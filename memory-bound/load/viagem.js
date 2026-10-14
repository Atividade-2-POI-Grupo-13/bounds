// Cada usuário virtual dirige viagens em sequência, como num app de navegação:
// inicia a viagem, dirige PAUSA_S segundos, recalcula a rota da posição atual,
// repete RECALCULOS vezes e avisa a chegada. Enquanto dirige, a viagem ocupa
// memória no servidor (a árvore de caminhos), mesmo sem fazer requisição.
//
// Os usuários começam espalhados ao longo da primeira viagem. O aquecimento
// padrão dura uma viagem.
//
// Variáveis: BASE_URL, VUS, DURATION, PONTOS, PAUSA_S, RECALCULOS, TIMEOUT, AQUECIMENTO_S
// Exemplo:
//   k6 run -e BASE_URL=http://localhost:8000 -e VUS=10 -e DURATION=60s load/viagem.js

import http from "k6/http";
import { check, sleep } from "k6";
import { BASE_URL, TIMEOUT, inicioDoTeste, marcas, opcoes, ponto, sortearPar } from "./comum.js";

const PAUSA_S = Number(__ENV.PAUSA_S || 5);
const RECALCULOS = Number(__ENV.RECALCULOS || 6);
const DURACAO_VIAGEM_S = PAUSA_S * (RECALCULOS + 1);
const AQUECIMENTO_S = Number(__ENV.AQUECIMENTO_S || DURACAO_VIAGEM_S);

export const options = opcoes(["inicio", "recalculo"]);

export function setup() {
  return inicioDoTeste();
}

export default function (dados) {
  if (__ITER === 0) {
    // Espalha o começo dos usuários, para as viagens não iniciarem todas juntas.
    sleep(Math.random() * DURACAO_VIAGEM_S);
  }
  const par = sortearPar();
  const inicio = http.post(
    `${BASE_URL}/viagens?origem=${ponto(par.origem)}&destino=${ponto(par.destino)}`,
    null,
    { timeout: TIMEOUT, tags: marcas(dados, "inicio", AQUECIMENTO_S) },
  );
  check(inicio, { "inicio 200": (r) => r.status === 200 });
  if (inicio.status !== 200) {
    sleep(PAUSA_S);
    return;
  }

  const viagem = inicio.json();
  const rota = viagem.rota;
  for (let k = 1; k <= RECALCULOS; k++) {
    sleep(PAUSA_S);
    // Avança pela rota original: no recálculo k, o carro está na fração k/(RECALCULOS+1) dela.
    const posicao = rota[Math.floor((rota.length * k) / (RECALCULOS + 1))];
    const r = http.get(`${BASE_URL}/viagens/${viagem.viagem}/rota?posicao=${ponto(posicao)}`, {
      timeout: TIMEOUT,
      tags: marcas(dados, "recalculo", AQUECIMENTO_S),
    });
    check(r, { "recalculo 200": (res) => res.status === 200 });
  }

  sleep(PAUSA_S);
  http.del(`${BASE_URL}/viagens/${viagem.viagem}`, null, {
    timeout: TIMEOUT,
    tags: marcas(dados, "fim", AQUECIMENTO_S),
  });
}
