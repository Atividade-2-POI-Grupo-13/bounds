package br.edu.ufcg.consumidor;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

/**
 * Consome jobs do buffer. Se o buffer estiver vazio, espera um pouco
 * e pergunta de novo, até conseguir ou desistir.
 */
@RestController
public class ConsumidorController {

    public record Resultado(int pedidos, int concluidos, long vezesVazio, long tempoMs) {}

    private final URI retirar;
    private final Duration espera;
    private final long desistirNanos;
    // HTTP/1.1: cada pergunta em andamento ocupa uma conexão (reaproveitada depois)
    private final HttpClient http = HttpClient.newBuilder()
            .version(HttpClient.Version.HTTP_1_1)
            .connectTimeout(Duration.ofSeconds(5))
            .build();

    public ConsumidorController(@Value("${consumidor.buffer.url:http://localhost:8080}") String bufferUrl,
                                @Value("${consumidor.espera-ms:100}") long esperaMs,
                                @Value("${consumidor.desistir-apos-ms:30000}") long desistirMs) {
        this.retirar = URI.create(bufferUrl.replaceAll("/+$", "") + "/retirar");
        this.espera = Duration.ofMillis(esperaMs);
        this.desistirNanos = Duration.ofMillis(desistirMs).toNanos();
    }

    @PostMapping("/consumir")
    public Resultado consumir(@RequestParam("jobs") int jobs) throws InterruptedException {
        if (jobs < 1 || jobs > 1_000_000) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Use jobs entre 1 e 1000000");
        }
        long inicio = System.nanoTime();
        long vezesVazio = 0;

        for (int concluidos = 0; concluidos < jobs; concluidos++) {
            long esperandoDesde = System.nanoTime();
            while (!tentarRetirar()) {
                vezesVazio++;
                if (System.nanoTime() - esperandoDesde > desistirNanos) {
                    // Ninguém produziu por tempo demais: devolve o que conseguiu fazer
                    return new Resultado(jobs, concluidos, vezesVazio, ms(inicio));
                }
                Thread.sleep(espera); // buffer vazio: espera e pergunta de novo
            }
        }
        return new Resultado(jobs, jobs, vezesVazio, ms(inicio));
    }

    /** true se retirou um job, false se o buffer estava vazio. */
    private boolean tentarRetirar() throws InterruptedException {
        HttpRequest requisicao = HttpRequest.newBuilder(retirar)
                .timeout(Duration.ofSeconds(10))
                .POST(HttpRequest.BodyPublishers.noBody())
                .build();
        int status;
        try {
            // A thread fica parada aqui enquanto o job inteiro chega pela rede (e é descartado)
            status = http.send(requisicao, HttpResponse.BodyHandlers.discarding()).statusCode();
        } catch (IOException e) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "Buffer fora do ar: " + e);
        }
        if (status == 200) {
            return true;
        }
        if (status == 204) {
            return false;
        }
        throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "Buffer respondeu " + status);
    }

    private static long ms(long inicioNanos) {
        return (System.nanoTime() - inicioNanos) / 1_000_000;
    }
}
