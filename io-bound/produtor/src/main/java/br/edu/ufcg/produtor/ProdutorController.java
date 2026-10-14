package br.edu.ufcg.produtor;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Random;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

/**
 * Produz jobs e coloca no buffer. Cada job leva um conteúdo de tamanho fixo,
 * para pesar na rede. Se o buffer estiver cheio, espera um pouco e pergunta
 * de novo (mandando o job inteiro outra vez), até conseguir ou desistir.
 */
@RestController
public class ProdutorController {

    public record Resultado(int pedidos, int concluidos, long vezesCheio, long tempoMs) {}

    private final AtomicLong proximoId = new AtomicLong();
    private final URI colocar;
    private final byte[] conteudo;
    private final Duration espera;
    private final long desistirNanos;
    // HTTP/1.1: cada pergunta em andamento ocupa uma conexão (reaproveitada depois)
    private final HttpClient http = HttpClient.newBuilder()
            .version(HttpClient.Version.HTTP_1_1)
            .connectTimeout(Duration.ofSeconds(5))
            .build();

    public ProdutorController(@Value("${produtor.buffer.url:http://localhost:8080}") String bufferUrl,
                              @Value("${produtor.job-kb:100}") int jobKb,
                              @Value("${produtor.espera-ms:100}") long esperaMs,
                              @Value("${produtor.desistir-apos-ms:30000}") long desistirMs) {
        this.colocar = URI.create(bufferUrl.replaceAll("/+$", "") + "/colocar");
        // Gerado uma vez só e reaproveitado em todo job: o custo fica na rede e no disco, não na CPU
        this.conteudo = new byte[jobKb * 1024];
        new Random(42).nextBytes(conteudo);
        this.espera = Duration.ofMillis(esperaMs);
        this.desistirNanos = Duration.ofMillis(desistirMs).toNanos();
    }

    @PostMapping("/produzir")
    public Resultado produzir(@RequestParam("jobs") int jobs) throws InterruptedException {
        if (jobs < 1 || jobs > 1_000_000) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Use jobs entre 1 e 1000000");
        }
        long inicio = System.nanoTime();
        long vezesCheio = 0;

        for (int concluidos = 0; concluidos < jobs; concluidos++) {
            String item = "job-" + proximoId.incrementAndGet();
            long esperandoDesde = System.nanoTime();
            while (!tentarColocar(item)) {
                vezesCheio++;
                if (System.nanoTime() - esperandoDesde > desistirNanos) {
                    // Ninguém consumiu por tempo demais: devolve o que conseguiu fazer
                    return new Resultado(jobs, concluidos, vezesCheio, ms(inicio));
                }
                Thread.sleep(espera); // buffer cheio: espera e pergunta de novo
            }
        }
        return new Resultado(jobs, jobs, vezesCheio, ms(inicio));
    }

    /** true se o buffer aceitou o item, false se estava cheio. */
    private boolean tentarColocar(String item) throws InterruptedException {
        HttpRequest requisicao = HttpRequest.newBuilder(colocar)
                .timeout(Duration.ofSeconds(10))
                .header("Content-Type", "application/octet-stream")
                .POST(HttpRequest.BodyPublishers.concat(
                        HttpRequest.BodyPublishers.ofString(item + "\n"),
                        HttpRequest.BodyPublishers.ofByteArray(conteudo)))
                .build();
        int status;
        try {
            // A thread fica parada aqui esperando a resposta do buffer pela rede
            status = http.send(requisicao, HttpResponse.BodyHandlers.discarding()).statusCode();
        } catch (IOException e) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "Buffer fora do ar: " + e);
        }
        if (status == 201) {
            return true;
        }
        if (status == 409) {
            return false;
        }
        throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "Buffer respondeu " + status);
    }

    private static long ms(long inicioNanos) {
        return (System.nanoTime() - inicioNanos) / 1_000_000;
    }
}
