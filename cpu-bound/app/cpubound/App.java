package cpubound;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;
import java.io.IOException;
import java.io.OutputStream;
import java.lang.management.ManagementFactory;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Aplicacao CPU-bound: servico de hash de senhas.
 *
 * Cada pedido calcula um hash PBKDF2, que repete uma funcao criptografica
 * milhares de vezes. O custo de CPU e proporcional ao parametro "iteracoes",
 * e o pedido nao usa disco nem aloca memoria relevante.
 *
 * Endpoints:
 *   GET /hash?senha=...&iteracoes=N                      gera salt e hash
 *   GET /verificar?senha=...&salt=...&hash=...&iteracoes=N   confere uma senha
 *   GET /health                                          estado do servidor
 *
 * Monitoramento, em outra porta (padrao 8081) e com uma thread propria, para
 * responder mesmo quando a fila de hashes esta cheia:
 *   GET /metrics   fila, threads ocupadas, pedidos, CPU e memoria do processo
 */
public class App {

    static final String ALGORITMO = "PBKDF2WithHmacSHA256";
    static final int ITERACOES_PADRAO = 100_000;
    static final int ITERACOES_MAXIMO = 10_000_000;
    static final int SENHA_MAXIMO = 1024;   // caracteres
    static final int SALT_BYTES = 16;
    static final int HASH_BITS = 256;

    static final SecureRandom SORTEIO = new SecureRandom();
    static final HexFormat HEX = HexFormat.of();

    static int threads;
    static ThreadPoolExecutor trabalhadores;
    static final AtomicLong PEDIDOS = new AtomicLong();   // respostas de /hash e /verificar
    static final AtomicLong ERROS = new AtomicLong();     // respostas 4xx e 5xx
    static final long INICIO_EPOCH_MS = System.currentTimeMillis();

    public static void main(String[] args) throws IOException {
        int porta = variavelInteira("PORT", 8080);
        // Uma thread de trabalho por processador: e isso que faz a capacidade
        // da aplicacao acompanhar o numero de vCPUs da maquina virtual.
        threads = variavelInteira("THREADS", Runtime.getRuntime().availableProcessors());

        HttpServer servidor = HttpServer.create(new InetSocketAddress(porta), 0);
        // Pedidos que chegam com todas as threads ocupadas esperam em fila.
        // E essa fila que faz o tempo de resposta crescer quando ha saturacao.
        trabalhadores = (ThreadPoolExecutor) Executors.newFixedThreadPool(threads);
        servidor.setExecutor(trabalhadores);
        servidor.createContext("/", App::atender);
        servidor.start();

        // Monitoramento num servidor separado, com uma thread so para ele: se
        // passasse pela fila dos hashes, demoraria justamente na saturacao.
        int portaMonitor = variavelInteira("MONITOR_PORT", 8081);
        HttpServer monitor = HttpServer.create(new InetSocketAddress(portaMonitor), 0);
        monitor.setExecutor(Executors.newSingleThreadExecutor());
        monitor.createContext("/metrics", pedido -> {
            try {
                responder(pedido, 200, metrics());
            } finally {
                pedido.close();
            }
        });
        monitor.start();

        System.out.printf("app-cpu no ar: porta %d, %d thread(s), %d processador(es), monitor na porta %d%n",
                porta, threads, Runtime.getRuntime().availableProcessors(), portaMonitor);
    }

    // ---------------------------------------------------------------- rotas

    static void atender(HttpExchange pedido) throws IOException {
        try {
            if (!"GET".equals(pedido.getRequestMethod())) {
                ERROS.incrementAndGet();
                responder(pedido, 405, "{\"erro\":\"use GET\"}");
                return;
            }
            Map<String, String> parametros = lerParametros(pedido.getRequestURI().getRawQuery());
            switch (pedido.getRequestURI().getPath()) {
                case "/health" -> responder(pedido, 200, health());
                case "/hash" -> {
                    responder(pedido, 200, gerar(parametros));
                    PEDIDOS.incrementAndGet();
                }
                case "/verificar" -> {
                    responder(pedido, 200, verificar(parametros));
                    PEDIDOS.incrementAndGet();
                }
                default -> {
                    ERROS.incrementAndGet();
                    responder(pedido, 404, "{\"erro\":\"rota inexistente\"}");
                }
            }
        } catch (IllegalArgumentException e) {
            ERROS.incrementAndGet();
            responder(pedido, 400, "{\"erro\":\"" + e.getMessage() + "\"}");
        } catch (Exception e) {
            ERROS.incrementAndGet();
            responder(pedido, 500, "{\"erro\":\"falha interna\"}");
        } finally {
            pedido.close();
        }
    }

    /**
     * Estado interno, lido a cada segundo durante os experimentos. A CPU e a
     * media desde a leitura anterior, em "100% = 1 nucleo", como no docker stats;
     * a memoria (RSS) e a que o processo ocupa de fato na RAM.
     */
    static String metrics() {
        double cpu = cpuDesdeUltimaLeitura();
        Runtime rt = Runtime.getRuntime();
        return String.format(Locale.ROOT,
                "{\"epoch\":%.3f,\"inicio_epoch\":%.3f,\"processadores\":%d,\"threads\":%d,"
                        + "\"threads_ocupadas\":%d,\"fila\":%d,\"pedidos\":%d,\"erros\":%d,"
                        + "\"cpu_percent\":%.1f,\"rss_mb\":%.1f,\"heap_usado_mb\":%.1f}",
                System.currentTimeMillis() / 1000.0, INICIO_EPOCH_MS / 1000.0,
                rt.availableProcessors(), threads, trabalhadores.getActiveCount(),
                trabalhadores.getQueue().size(), PEDIDOS.get(), ERROS.get(), cpu,
                rssMb(), (rt.totalMemory() - rt.freeMemory()) / 1048576.0);
    }

    static long ultimaCpuNs = 0;
    static long ultimoRelogioNs = System.nanoTime();

    /**
     * Tempo de CPU gasto pelo processo desde a leitura anterior, dividido pelo
     * tempo que passou: 100% = 1 nucleo ocupado o tempo todo. (O getProcessCpuLoad
     * do Java divide pelas CPUs da maquina inteira, nao pelas que o processo pode usar.)
     */
    static synchronized double cpuDesdeUltimaLeitura() {
        var so = (com.sun.management.OperatingSystemMXBean) ManagementFactory.getOperatingSystemMXBean();
        long cpuNs = so.getProcessCpuTime();
        long relogioNs = System.nanoTime();
        double percentual = 100.0 * (cpuNs - ultimaCpuNs) / Math.max(1, relogioNs - ultimoRelogioNs);
        ultimaCpuNs = cpuNs;
        ultimoRelogioNs = relogioNs;
        return percentual;
    }

    /** Memoria residente do processo, de /proc/self/status (Linux). -1 em outros sistemas. */
    static double rssMb() {
        try {
            for (String linha : Files.readAllLines(Path.of("/proc/self/status"))) {
                if (linha.startsWith("VmRSS:")) {
                    return Long.parseLong(linha.replaceAll("\\D", "")) / 1024.0;
                }
            }
        } catch (IOException | RuntimeException e) {
            // sem /proc: fora do Linux
        }
        return -1;
    }

    static String health() {
        return String.format(Locale.ROOT,
                "{\"status\":\"ok\",\"processadores\":%d,\"threads\":%d}",
                Runtime.getRuntime().availableProcessors(), threads);
    }

    /** Gera um salt aleatorio e calcula o hash da senha. */
    static String gerar(Map<String, String> p) throws GeneralSecurityException {
        char[] senha = lerSenha(p);
        int iteracoes = lerIteracoes(p);
        byte[] salt = new byte[SALT_BYTES];
        SORTEIO.nextBytes(salt);

        long inicio = System.nanoTime();
        byte[] hash = pbkdf2(senha, salt, iteracoes);
        double ms = (System.nanoTime() - inicio) / 1e6;

        return String.format(Locale.ROOT,
                "{\"algoritmo\":\"%s\",\"iteracoes\":%d,\"salt\":\"%s\",\"hash\":\"%s\",\"tempo_ms\":%.1f}",
                ALGORITMO, iteracoes, HEX.formatHex(salt), HEX.formatHex(hash), ms);
    }

    /** Recalcula o hash com o salt informado e compara com o hash informado. */
    static String verificar(Map<String, String> p) throws GeneralSecurityException {
        char[] senha = lerSenha(p);
        int iteracoes = lerIteracoes(p);
        byte[] salt = lerHex(p, "salt");
        byte[] esperado = lerHex(p, "hash");

        long inicio = System.nanoTime();
        byte[] calculado = pbkdf2(senha, salt, iteracoes);
        double ms = (System.nanoTime() - inicio) / 1e6;

        // Comparacao em tempo constante, para nao revelar onde os hashes diferem.
        boolean confere = MessageDigest.isEqual(calculado, esperado);
        return String.format(Locale.ROOT, "{\"confere\":%b,\"tempo_ms\":%.1f}", confere, ms);
    }

    // ------------------------------------------------- o trabalho de CPU

    static byte[] pbkdf2(char[] senha, byte[] salt, int iteracoes) throws GeneralSecurityException {
        PBEKeySpec especificacao = new PBEKeySpec(senha, salt, iteracoes, HASH_BITS);
        try {
            return SecretKeyFactory.getInstance(ALGORITMO).generateSecret(especificacao).getEncoded();
        } finally {
            especificacao.clearPassword();
        }
    }

    // ------------------------------------------------------- parametros

    static char[] lerSenha(Map<String, String> p) {
        String senha = p.get("senha");
        if (senha == null || senha.isEmpty()) {
            throw new IllegalArgumentException("parametro senha obrigatorio");
        }
        if (senha.length() > SENHA_MAXIMO) {
            throw new IllegalArgumentException("senha longa demais");
        }
        return senha.toCharArray();
    }

    static int lerIteracoes(Map<String, String> p) {
        String texto = p.get("iteracoes");
        if (texto == null) {
            return ITERACOES_PADRAO;
        }
        int valor;
        try {
            valor = Integer.parseInt(texto);
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException("iteracoes deve ser um numero inteiro");
        }
        if (valor < 1 || valor > ITERACOES_MAXIMO) {
            throw new IllegalArgumentException("iteracoes deve estar entre 1 e " + ITERACOES_MAXIMO);
        }
        return valor;
    }

    static byte[] lerHex(Map<String, String> p, String nome) {
        String texto = p.get(nome);
        if (texto == null || texto.isEmpty()) {
            throw new IllegalArgumentException("parametro " + nome + " obrigatorio");
        }
        try {
            return HEX.parseHex(texto);
        } catch (IllegalArgumentException e) {
            throw new IllegalArgumentException("parametro " + nome + " deve estar em hexadecimal");
        }
    }

    static Map<String, String> lerParametros(String consulta) {
        Map<String, String> parametros = new HashMap<>();
        if (consulta == null || consulta.isEmpty()) {
            return parametros;
        }
        try {
            for (String par : consulta.split("&")) {
                int igual = par.indexOf('=');
                if (igual > 0) {
                    parametros.put(
                            URLDecoder.decode(par.substring(0, igual), StandardCharsets.UTF_8),
                            URLDecoder.decode(par.substring(igual + 1), StandardCharsets.UTF_8));
                }
            }
        } catch (IllegalArgumentException e) {
            throw new IllegalArgumentException("parametros mal codificados");
        }
        return parametros;
    }

    static int variavelInteira(String nome, int padrao) {
        String texto = System.getenv(nome);
        return (texto == null || texto.isBlank()) ? padrao : Integer.parseInt(texto.trim());
    }

    // --------------------------------------------------------- resposta

    static void responder(HttpExchange pedido, int status, String json) throws IOException {
        byte[] corpo = json.getBytes(StandardCharsets.UTF_8);
        pedido.getResponseHeaders().set("Content-Type", "application/json; charset=utf-8");
        pedido.sendResponseHeaders(status, corpo.length);
        try (OutputStream saida = pedido.getResponseBody()) {
            saida.write(corpo);
        }
    }
}
