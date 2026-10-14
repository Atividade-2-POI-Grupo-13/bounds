"""Contadores da aplicação e uso de memória/CPU do processo e da máquina (exposto em /metrics).

Os dados da máquina inteira (memória, swap, CPU) deixam o hospedeiro monitorar a VM
só pela porta da aplicação, mesmo sem ssh.
"""

import logging
import resource
import sys
import threading
import time
from contextlib import contextmanager

import psutil

log = logging.getLogger("rotas")

_processo = psutil.Process()
# A primeira leitura de CPU do psutil sempre dá 0: faz agora, para o primeiro /metrics já valer.
_processo.cpu_percent(interval=None)
psutil.cpu_percent(interval=None)
_trava = threading.Lock()
_inicio = time.time()

_em_andamento = 0  # requisições dentro do servidor agora (inclui as que estão na fila)
_na_fila = 0       # parte delas esperando vaga (só quando MAX_CONCURRENT > 0)
_total = 0
_erros = 0


def rss_mb() -> float:
    return _processo.memory_info().rss / 1_000_000


def pico_rss_mb() -> float:
    pico = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # No Linux ru_maxrss vem em KB; no macOS, em bytes.
    if sys.platform == "darwin":
        return pico / 1_000_000
    return pico / 1000


@contextmanager
def na_fila():
    """Conta a requisição como "na fila" enquanto espera o semáforo."""
    global _na_fila
    with _trava:
        _na_fila += 1
    try:
        yield
    finally:
        with _trava:
            _na_fila -= 1


@contextmanager
def track(endpoint: str):
    """Mede uma requisição: conta em andamento, total, erros, e loga a duração.

    Quem usa pode preencher info["nos_visitados"] para sair no log.
    """
    global _em_andamento, _total, _erros
    with _trava:
        _em_andamento += 1
    inicio = time.perf_counter()
    info: dict = {}
    status = "ok"
    try:
        yield info
    except BaseException:
        status = "erro"
        raise
    finally:
        duracao_ms = (time.perf_counter() - inicio) * 1000
        with _trava:
            _em_andamento -= 1
            _total += 1
            if status == "erro":
                _erros += 1
        log.info("%s %s %.0fms visitados=%s", endpoint, status, duracao_ms, info.get("nos_visitados", "-"))


def snapshot() -> dict:
    with _trava:
        em_andamento = _em_andamento
        na_fila_agora = _na_fila
        total = _total
        erros = _erros
    return {
        "rss_mb": round(rss_mb(), 1),
        "pico_rss_mb": round(pico_rss_mb(), 1),
        # % de CPU do processo desde a última consulta (100 = um núcleo inteiro).
        "cpu_percent": _processo.cpu_percent(interval=None),
        "em_andamento": em_andamento,
        "na_fila": na_fila_agora,
        "total": total,
        "erros": erros,
        "uptime_s": round(time.time() - _inicio, 1),
        # Muda quando o processo reinicia (por exemplo, morto por falta de memória).
        "inicio_epoch": int(_inicio),
        "sistema": sistema(),
    }


def sistema() -> dict:
    """Memória, swap e CPU da máquina inteira (na VM: a VM toda)."""
    memoria = psutil.virtual_memory()
    swap = psutil.swap_memory()
    return {
        "mem_total_mb": round(memoria.total / 1_000_000, 1),
        "mem_usada_mb": round((memoria.total - memoria.available) / 1_000_000, 1),
        "mem_disponivel_mb": round(memoria.available / 1_000_000, 1),
        "swap_total_mb": round(swap.total / 1_000_000, 1),
        "swap_usado_mb": round(swap.used / 1_000_000, 1),
        # % de CPU da máquina desde a última consulta (100 = todos os núcleos ocupados).
        "cpu_percent": psutil.cpu_percent(interval=None),
        "cpus": psutil.cpu_count(),
    }
