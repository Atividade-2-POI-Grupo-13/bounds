import java.io.IOException;
import java.io.PrintWriter;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Duration;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Queue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.locks.LockSupport;

/**
 * Gerador de carga em laco aberto.
 *
 * Envia pedidos a uma taxa constante, sem esperar as respostas: o pedido
 * numero i sai no instante i / taxa, esteja o servidor livre ou nao. Assim,
 * quando o servidor satura, os pedidos se acumulam na fila dele e o tempo de
 * resposta cresce, que e o que o experimento quer medir. Um gerador que espera
 * cada resposta antes de mandar o proximo pedido (laco fechado) desaceleraria
 * junto com o servidor e esconderia essa degradacao.
 *
 * Os pedidos enviados durante o aquecimento sao registrados, mas ficam fora
 * das estatisticas.
 *
 * Uso (nao precisa compilar):
 *   java Carga.java url=URL taxa=N [duracao=S] [aquecimento=S] [timeout=S]
 *                   [saida=pedidos.csv] [resumo=resumo.csv]
 *
 * Modo continuo: envia sem prazo, ate Ctrl+C, e mostra uma linha a cada
 * intervalo, como um site que recebe usuarios o tempo todo. Nao grava arquivos.
 *   java Carga.java url=URL taxa=N modo=continuo [intervalo=S] [timeout=S]
 *
 * Exemplos:
 *   java Carga.java "url=http://localhost:8080/hash?senha=x&iteracoes=100000" taxa=20 duracao=60
 *   java Carga.java "url=http://localhost:8080/hash?senha=x&iteracoes=100000" taxa=20 modo=continuo
 */
public class Carga {

    /** O que aconteceu com um pedido. Tempos em nanossegundos de System.nanoTime(). */
    record Resultado(long numero, long envio, long fim, int status, String erro, boolean aquecimento) {
        double latenciaMs() {
            return (fim - envio) / 1e6;
        }
    }

    public static void main(String[] args) throws IOException {
        Map<String, String> a = lerArgumentos(args);
        URI url = URI.create(obrigatorio(a, "url"));
        double taxa = Double.parseDouble(obrigatorio(a, "taxa"));   // pedidos por segundo
        int duracao = inteiro(a, "duracao", 60);                    // segundos medidos
        int aquecimento = inteiro(a, "aquecimento", 10);            // segundos descartados
        int timeout = inteiro(a, "timeout", 60);                    // segundos por pedido
        if (taxa <= 0 || duracao <= 0 || aquecimento < 0 || timeout <= 0) {
            throw new IllegalArgumentException("taxa, duracao e timeout devem ser positivos");
        }

        HttpClient cliente = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofSeconds(10))
                .build();
        HttpRequest pedido = HttpRequest.newBuilder(url)
                .timeout(Duration.ofSeconds(timeout))
                .GET()
                .build();

        if ("continuo".equals(a.get("modo"))) {
            rodarContinuo(cliente, pedido, taxa, inteiro(a, "intervalo", 5));
            return;
        }

        long intervalo = Math.round(1e9 / taxa);
        long pedidosAquecimento = Math.round(taxa * aquecimento);
        long total = pedidosAquecimento + Math.round(taxa * duracao);

        System.out.printf(Locale.ROOT, "Enviando %.1f pedidos/s: %ds de aquecimento + %ds medidos (%d pedidos)%n",
                taxa, aquecimento, duracao, total);

        Queue<Resultado> resultados = new ConcurrentLinkedQueue<>();
        List<CompletableFuture<?>> pendentes = new ArrayList<>();
        long atrasoMaximo = 0;

        long inicioEpochMs = System.currentTimeMillis();
        long inicio = System.nanoTime();
        for (long i = 0; i < total; i++) {
            // Espera o instante previsto para este pedido. Se o gerador estiver
            // atrasado, envia na hora, e a taxa media se mantem.
            long previsto = inicio + i * intervalo;
            long agora;
            while ((agora = System.nanoTime()) < previsto) {
                LockSupport.parkNanos(previsto - agora);
            }
            atrasoMaximo = Math.max(atrasoMaximo, agora - previsto);

            long numero = i;
            boolean descartado = i < pedidosAquecimento;
            long envio = System.nanoTime();
            pendentes.add(cliente.sendAsync(pedido, HttpResponse.BodyHandlers.discarding())
                    .whenComplete((resposta, erro) -> resultados.add(new Resultado(
                            numero, envio, System.nanoTime(),
                            resposta == null ? -1 : resposta.statusCode(),
                            erro == null ? "" : nomeDoErro(erro),
                            descartado))));
        }

        long inicioJanela = inicio + aquecimento * 1_000_000_000L;
        long fimJanela = inicioJanela + duracao * 1_000_000_000L;
        System.out.println("Envio terminado. Esperando as respostas pendentes...");
        try {
            CompletableFuture.allOf(pendentes.toArray(new CompletableFuture[0])).join();
        } catch (CompletionException e) {
            // Os erros ja foram registrados em cada Resultado.
        }

        List<Resultado> todos = new ArrayList<>(resultados);
        todos.sort((x, y) -> Long.compare(x.numero(), y.numero()));
        Map<String, Object> estatisticas = calcular(todos, taxa, inicioJanela, fimJanela, duracao);
        estatisticas.put("atraso_max_ms", atrasoMaximo / 1e6);
        // Janela medida em segundos desde 1970 (epoch), para cruzar com outras coletas.
        estatisticas.put("janela_inicio_epoch", (inicioEpochMs + aquecimento * 1000L) / 1000.0);
        estatisticas.put("janela_fim_epoch", (inicioEpochMs + (aquecimento + duracao) * 1000L) / 1000.0);

        imprimir(estatisticas);
        if (atrasoMaximo > 10_000_000L) {
            System.out.println("AVISO: o gerador atrasou mais de 10 ms em algum envio. "
                    + "A taxa pode nao ter sido mantida; veja se o hospedeiro esta sobrecarregado.");
        }
        if (a.containsKey("saida")) {
            gravarPedidos(Path.of(a.get("saida")), todos, inicio);
        }
        if (a.containsKey("resumo")) {
            gravarResumo(Path.of(a.get("resumo")), url, aquecimento, duracao, estatisticas);
        }
        // O HttpClient do Java 17 nao tem close(); encerra as threads dele aqui.
        System.exit(0);
    }

    // --------------------------------------------------------- modo continuo

    /** Envia a taxa constante ate o processo ser interrompido, com um resumo por intervalo. */
    static void rodarContinuo(HttpClient cliente, HttpRequest pedido, double taxa, int intervalo) {
        if (intervalo <= 0) {
            throw new IllegalArgumentException("intervalo deve ser positivo");
        }
        // Tempos das respostas que chegaram no intervalo atual; esvaziado a cada linha.
        Queue<Double> latencias = new ConcurrentLinkedQueue<>();
        AtomicLong enviadosNoIntervalo = new AtomicLong();
        AtomicLong errosNoIntervalo = new AtomicLong();
        AtomicLong semResposta = new AtomicLong();
        AtomicLong totalEnviados = new AtomicLong();
        AtomicLong totalOk = new AtomicLong();
        AtomicLong totalErros = new AtomicLong();

        System.out.printf(Locale.ROOT, "Enviando %.1f pedidos/s sem prazo. Ctrl+C para parar.%n", taxa);
        System.out.printf("%-8s  %11s  %11s  %8s  %8s  %6s  %6s%n",
                "hora", "enviados/s", "respostas/s", "p50 ms", "p95 ms", "erros", "fila");

        ScheduledExecutorService relogio = Executors.newSingleThreadScheduledExecutor(tarefa -> {
            Thread t = new Thread(tarefa);
            t.setDaemon(true);
            return t;
        });
        relogio.scheduleAtFixedRate(() -> {
            List<Double> tempos = new ArrayList<>();
            for (Double ms; (ms = latencias.poll()) != null; ) {
                tempos.add(ms);
            }
            double[] ordenados = tempos.stream().mapToDouble(Double::doubleValue).sorted().toArray();
            System.out.printf(Locale.ROOT, "%-8s  %11.1f  %11.1f  %8.1f  %8.1f  %6d  %6d%n",
                    LocalTime.now().format(DateTimeFormatter.ofPattern("HH:mm:ss")),
                    enviadosNoIntervalo.getAndSet(0) / (double) intervalo,
                    ordenados.length / (double) intervalo,
                    percentil(ordenados, 50), percentil(ordenados, 95),
                    errosNoIntervalo.getAndSet(0), semResposta.get());
        }, intervalo, intervalo, TimeUnit.SECONDS);

        // Ao apertar Ctrl+C, a JVM roda este gancho antes de sair.
        Runtime.getRuntime().addShutdownHook(new Thread(() -> System.out.printf(
                "%nEncerrado. Total: %d enviados, %d respostas ok, %d erros, %d sem resposta.%n",
                totalEnviados.get(), totalOk.get(), totalErros.get(), semResposta.get())));

        long passo = Math.round(1e9 / taxa);
        long inicio = System.nanoTime();
        for (long i = 0; ; i++) {
            long previsto = inicio + i * passo;
            long agora;
            while ((agora = System.nanoTime()) < previsto) {
                LockSupport.parkNanos(previsto - agora);
            }
            enviadosNoIntervalo.incrementAndGet();
            totalEnviados.incrementAndGet();
            semResposta.incrementAndGet();
            long envio = System.nanoTime();
            cliente.sendAsync(pedido, HttpResponse.BodyHandlers.discarding())
                    .whenComplete((resposta, erro) -> {
                        semResposta.decrementAndGet();
                        if (erro == null && resposta.statusCode() == 200) {
                            latencias.add((System.nanoTime() - envio) / 1e6);
                            totalOk.incrementAndGet();
                        } else {
                            errosNoIntervalo.incrementAndGet();
                            totalErros.incrementAndGet();
                        }
                    });
        }
    }

    // ----------------------------------------------------------- estatisticas

    static Map<String, Object> calcular(List<Resultado> todos, double taxa,
                                        long inicioJanela, long fimJanela, int duracao) {
        List<Resultado> medidos = todos.stream().filter(r -> !r.aquecimento()).toList();
        double[] latencias = medidos.stream()
                .filter(r -> r.status() == 200)
                .mapToDouble(Resultado::latenciaMs)
                .sorted()
                .toArray();

        // Vazao: respostas bem-sucedidas que chegaram dentro da janela medida,
        // por segundo. Quando o servidor satura, ela para de acompanhar a taxa enviada.
        long concluidosNaJanela = todos.stream()
                .filter(r -> r.status() == 200 && r.fim() >= inicioJanela && r.fim() < fimJanela)
                .count();
        // Pedidos enviados ate o fim da janela que ainda nao tinham resposta nesse instante.
        long semRespostaNoFim = todos.stream()
                .filter(r -> r.envio() < fimJanela && r.fim() >= fimJanela)
                .count();

        Map<String, Object> e = new LinkedHashMap<>();
        e.put("taxa", taxa);
        e.put("enviados", (long) medidos.size());
        e.put("ok", (long) latencias.length);
        e.put("erros", medidos.size() - (long) latencias.length);
        e.put("vazao", concluidosNaJanela / (double) duracao);
        e.put("media_ms", latencias.length == 0 ? Double.NaN : Arrays.stream(latencias).average().orElseThrow());
        e.put("p50_ms", percentil(latencias, 50));
        e.put("p95_ms", percentil(latencias, 95));
        e.put("p99_ms", percentil(latencias, 99));
        e.put("max_ms", latencias.length == 0 ? Double.NaN : latencias[latencias.length - 1]);
        e.put("sem_resposta_no_fim", semRespostaNoFim);
        return e;
    }

    /** Percentil pelo metodo do posto mais proximo, sobre valores ja ordenados. */
    static double percentil(double[] ordenados, double p) {
        if (ordenados.length == 0) {
            return Double.NaN;
        }
        int posicao = (int) Math.ceil(p / 100 * ordenados.length) - 1;
        return ordenados[Math.max(0, posicao)];
    }

    // ----------------------------------------------------------------- saida

    static void imprimir(Map<String, Object> e) {
        System.out.printf(Locale.ROOT, "%nTaxa enviada:        %.1f pedidos/s%n", (double) e.get("taxa"));
        System.out.printf(Locale.ROOT, "Vazao obtida:        %.1f respostas/s%n", (double) e.get("vazao"));
        System.out.printf(Locale.ROOT, "Pedidos medidos:     %d (%d ok, %d com erro)%n",
                (long) e.get("enviados"), (long) e.get("ok"), (long) e.get("erros"));
        System.out.printf(Locale.ROOT, "Tempo de resposta:   media %.1f ms | p50 %.1f | p95 %.1f | p99 %.1f | max %.1f%n",
                (double) e.get("media_ms"), (double) e.get("p50_ms"), (double) e.get("p95_ms"),
                (double) e.get("p99_ms"), (double) e.get("max_ms"));
        System.out.printf(Locale.ROOT, "Sem resposta ao fim: %d pedidos%n", (long) e.get("sem_resposta_no_fim"));
        System.out.printf(Locale.ROOT, "Atraso max. do gerador: %.1f ms%n", (double) e.get("atraso_max_ms"));
    }

    /** Uma linha por pedido, com o instante de envio contado a partir do inicio do teste. */
    static void gravarPedidos(Path arquivo, List<Resultado> todos, long inicio) throws IOException {
        criarPasta(arquivo);
        try (PrintWriter w = new PrintWriter(Files.newBufferedWriter(arquivo))) {
            w.println("numero,envio_ms,latencia_ms,status,fase,erro");
            for (Resultado r : todos) {
                w.printf(Locale.ROOT, "%d,%.3f,%.3f,%d,%s,%s%n",
                        r.numero(), (r.envio() - inicio) / 1e6, r.latenciaMs(), r.status(),
                        r.aquecimento() ? "aquecimento" : "medido", r.erro());
            }
        }
        System.out.println("Pedidos gravados em " + arquivo);
    }

    /** Acrescenta uma linha ao arquivo de resumo, criando o cabecalho se ele for novo. */
    static void gravarResumo(Path arquivo, URI url, int aquecimento, int duracao, Map<String, Object> e)
            throws IOException {
        criarPasta(arquivo);
        boolean novo = !Files.exists(arquivo);
        StringBuilder linha = new StringBuilder();
        if (novo) {
            linha.append("data_hora,url,aquecimento_s,duracao_s,").append(String.join(",", e.keySet())).append('\n');
        }
        linha.append(LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss")))
                .append(",\"").append(url).append("\",").append(aquecimento).append(',').append(duracao);
        for (Object valor : e.values()) {
            linha.append(',').append(valor instanceof Double d ? String.format(Locale.ROOT, "%.3f", d) : valor);
        }
        linha.append('\n');
        Files.writeString(arquivo, linha, StandardOpenOption.CREATE, StandardOpenOption.APPEND);
        System.out.println("Resumo acrescentado a " + arquivo);
    }

    static void criarPasta(Path arquivo) throws IOException {
        Path pasta = arquivo.toAbsolutePath().getParent();
        if (pasta != null) {
            Files.createDirectories(pasta);
        }
    }

    // ------------------------------------------------------------ argumentos

    static Map<String, String> lerArgumentos(String[] args) {
        Map<String, String> a = new HashMap<>();
        for (String arg : args) {
            int igual = arg.indexOf('=');
            if (igual <= 0) {
                throw new IllegalArgumentException("argumento deve ter a forma chave=valor: " + arg);
            }
            a.put(arg.substring(0, igual), arg.substring(igual + 1));
        }
        return a;
    }

    static String obrigatorio(Map<String, String> a, String chave) {
        String valor = a.get(chave);
        if (valor == null || valor.isEmpty()) {
            throw new IllegalArgumentException("falta o argumento " + chave + "=...");
        }
        return valor;
    }

    static int inteiro(Map<String, String> a, String chave, int padrao) {
        return a.containsKey(chave) ? Integer.parseInt(a.get(chave)) : padrao;
    }

    static String nomeDoErro(Throwable erro) {
        Throwable causa = erro instanceof CompletionException && erro.getCause() != null ? erro.getCause() : erro;
        return causa.getClass().getSimpleName();
    }
}
