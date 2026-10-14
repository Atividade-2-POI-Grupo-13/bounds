package br.edu.ufcg.buffer;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicLong;
import java.util.stream.Stream;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

/**
 * Buffer de tamanho fixo guardado em disco: cada job vira um arquivo em data/.
 * Nunca faz ninguém esperar: se está cheio ou vazio, responde na hora e quem
 * chamou que tente de novo mais tarde.
 */
@RestController
public class BufferController {

    public record Estado(int tamanho, int capacidade, long colocados, long retirados,
                         long recusasCheio, long recusasVazio) {}

    private final Path dir;
    private final boolean fsync;
    private final int capacidade;
    private final Semaphore vagas;
    // Jobs já gravados, na ordem em que ficaram prontos
    private final ConcurrentLinkedQueue<Path> fila = new ConcurrentLinkedQueue<>();
    private final AtomicLong proximoArquivo = new AtomicLong();
    private final AtomicLong colocados = new AtomicLong();
    private final AtomicLong retirados = new AtomicLong();
    private final AtomicLong recusasCheio = new AtomicLong();
    private final AtomicLong recusasVazio = new AtomicLong();

    public BufferController(@Value("${buffer.capacidade:10}") int capacidade,
                            @Value("${buffer.dir:data}") String dir,
                            @Value("${buffer.fsync:true}") boolean fsync) throws IOException {
        this.capacidade = capacidade;
        this.vagas = new Semaphore(capacidade);
        this.fsync = fsync;
        this.dir = Files.createDirectories(Path.of(dir));
        // O buffer começa vazio a cada execução: apaga os jobs que sobraram da anterior
        try (Stream<Path> antigos = Files.list(this.dir)) {
            for (Path antigo : antigos.filter(p -> p.toString().endsWith(".job")).toList()) {
                Files.delete(antigo);
            }
        }
    }

    /** 201 se gravou o job, 409 se o buffer está cheio. */
    @PostMapping("/colocar")
    public ResponseEntity<Void> colocar(@RequestBody byte[] job) throws IOException {
        if (!vagas.tryAcquire()) {
            recusasCheio.incrementAndGet();
            return ResponseEntity.status(HttpStatus.CONFLICT).build();
        }
        Path arquivo = dir.resolve(proximoArquivo.incrementAndGet() + ".job");
        try {
            gravar(arquivo, job);
        } catch (IOException e) {
            Files.deleteIfExists(arquivo);
            vagas.release();
            throw e;
        }
        fila.add(arquivo);
        colocados.incrementAndGet();
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }

    /** 200 com o job mais antigo (lido do disco e apagado), 204 se o buffer está vazio. */
    @PostMapping("/retirar")
    public ResponseEntity<byte[]> retirar() throws IOException {
        Path arquivo = fila.poll();
        if (arquivo == null) {
            recusasVazio.incrementAndGet();
            return ResponseEntity.noContent().build();
        }
        byte[] job;
        try {
            job = Files.readAllBytes(arquivo);
            Files.delete(arquivo);
        } finally {
            vagas.release();
        }
        retirados.incrementAndGet();
        return ResponseEntity.ok().contentType(MediaType.APPLICATION_OCTET_STREAM).body(job);
    }

    @GetMapping("/estado")
    public Estado estado() {
        return new Estado(fila.size(), capacidade, colocados.get(), retirados.get(),
                recusasCheio.get(), recusasVazio.get());
    }

    private void gravar(Path arquivo, byte[] job) throws IOException {
        ByteBuffer bytes = ByteBuffer.wrap(job);
        try (FileChannel canal = FileChannel.open(arquivo,
                StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)) {
            while (bytes.hasRemaining()) {
                canal.write(bytes);
            }
            if (fsync) {
                canal.force(true); // espera o disco confirmar a gravação
            }
        }
    }
}
