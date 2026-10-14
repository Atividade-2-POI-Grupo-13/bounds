"""Monitor da VM, num processo separado da aplicação. Só biblioteca padrão (python3 do sistema).

GET / devolve JSON com memória, swap e CPU da VM (lidos de /proc) e RSS e hora de
início do processo da aplicação. Por ser outro processo, responde mesmo quando a
aplicação está com todas as threads ocupadas (disputando o GIL), em swap pesado
ou reiniciando depois de ser morta por falta de memória.

Instalado pelo install.sh como serviço rotas-monitor, na porta 8001
(no hospedeiro: 8081). Os experimentos sem ssh e o experiments/acompanhar.sh leem daqui.
"""

import json
import os
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

PORTA = int(os.environ.get("MONITOR_PORTA", "8001"))
TICKS_POR_SEGUNDO = os.sysconf("SC_CLK_TCK")

_cpu_anterior = None  # (ocioso, total) da consulta anterior


def ler_meminfo() -> dict[str, int]:
    """Campos de /proc/meminfo, em bytes."""
    campos: dict[str, int] = {}
    with open("/proc/meminfo") as f:
        for linha in f:
            nome, resto = linha.split(":", 1)
            campos[nome] = int(resto.split()[0]) * 1024
    return campos


def ler_cpu() -> tuple[int, int, int]:
    """(ocioso, total) em ticks desde o boot, e hora do boot (epoch)."""
    ocioso = 0
    total = 0
    boot = 0
    with open("/proc/stat") as f:
        for linha in f:
            partes = linha.split()
            if partes[0] == "cpu":
                valores = []
                for p in partes[1:]:
                    valores.append(int(p))
                ocioso = valores[3] + valores[4]  # idle + iowait
                total = sum(valores)
            elif partes[0] == "btime":
                boot = int(partes[1])
    return ocioso, total, boot


def processo_app() -> int | None:
    """PID do processo da aplicação (python -m app.main), ou None se não estiver rodando."""
    for nome in os.listdir("/proc"):
        if not nome.isdigit():
            continue
        try:
            with open(f"/proc/{nome}/cmdline", "rb") as f:
                comando = f.read().replace(b"\0", b" ")
        except OSError:
            continue
        if b"-m app.main" in comando:
            return int(nome)
    return None


def dados_app(pid: int, boot: int) -> tuple[float, int] | None:
    """(RSS em MB, hora de início em epoch) do processo, ou None se ele sumiu."""
    try:
        rss_mb = 0.0
        with open(f"/proc/{pid}/status") as f:
            for linha in f:
                if linha.startswith("VmRSS:"):
                    rss_mb = int(linha.split()[1]) * 1024 / 1_000_000
        with open(f"/proc/{pid}/stat") as f:
            # O nome do processo vem entre parênteses e pode ter espaços: corta depois dele.
            depois_do_nome = f.read().rsplit(")", 1)[1].split()
        inicio_ticks = int(depois_do_nome[19])  # campo 22 de /proc/PID/stat
    except (OSError, IndexError, ValueError):
        return None
    return rss_mb, boot + inicio_ticks // TICKS_POR_SEGUNDO


def coletar() -> dict:
    global _cpu_anterior
    memoria = ler_meminfo()
    ocioso, total, boot = ler_cpu()
    cpu_percent = 0.0
    if _cpu_anterior is not None and total > _cpu_anterior[1]:
        ocupado = (total - _cpu_anterior[1]) - (ocioso - _cpu_anterior[0])
        cpu_percent = 100 * ocupado / (total - _cpu_anterior[1])
    _cpu_anterior = (ocioso, total)

    resultado = {
        "tempo": int(time.time()),
        "rss_mb": None,
        "inicio_epoch": None,
        "sistema": {
            "mem_total_mb": round(memoria["MemTotal"] / 1_000_000, 1),
            "mem_usada_mb": round((memoria["MemTotal"] - memoria["MemAvailable"]) / 1_000_000, 1),
            "mem_disponivel_mb": round(memoria["MemAvailable"] / 1_000_000, 1),
            "swap_total_mb": round(memoria["SwapTotal"] / 1_000_000, 1),
            "swap_usado_mb": round((memoria["SwapTotal"] - memoria["SwapFree"]) / 1_000_000, 1),
            "cpu_percent": round(cpu_percent, 1),
            "cpus": os.cpu_count(),
        },
    }
    pid = processo_app()
    if pid is not None:
        dados = dados_app(pid, boot)
        if dados is not None:
            resultado["rss_mb"] = round(dados[0], 1)
            resultado["inicio_epoch"] = dados[1]
    return resultado


class Monitor(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        # JSON compacto ("campo":valor), como o da aplicação: os scripts leem com grep.
        corpo = json.dumps(coletar(), separators=(",", ":")).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, formato: str, *args) -> None:
        pass  # sem log por requisição: é consultado a cada segundo


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", PORTA), Monitor).serve_forever()
