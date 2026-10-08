// Cada usuário virtual dirige viagens em sequência, como num app de navegação:
// inicia a viagem, dirige PAUSA_S segundos, recalcula a rota da posição atual,
// repete RECALCULOS vezes e avisa a chegada. Enquanto dirige, a viagem ocupa
// memória no servidor (a árvore de caminhos), mesmo sem fazer requisição.
//
// Os usuários começam espalhados ao longo da primeira viagem. As requisições dos
// primeiros AQUECIMENTO_S segundos levam a marca fase=aquecimento e ficam fora
// das métricas de medição (fase=medicao).
//
// Variáveis: BASE_URL, VUS, DURATION, PONTOS, PAUSA_S, RECALCULOS, TIMEOUT, AQUECIMENTO_S
// Exemplo:
//   k6 run -e BASE_URL=http://localhost:8000 -e VUS=10 -e DURATION=60s load/viagem.js

import http from "k6/http";
import { check, sleep } from "k6";
import { SharedArray } from "k6/data";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const PAUSA_S = Number(__ENV.PAUSA_S || 5);
const RECALCULOS = Number(__ENV.RECALCULOS || 6);
const TIMEOUT = __ENV.TIMEOUT || "30s";
const DURACAO_VIAGEM_S = PAUSA_S * (RECALCULOS + 1);
const AQUECIMENTO_S = Number(__ENV.AQUECIMENTO_S || DURACAO_VIAGEM_S);

const pares = new SharedArray("pares", function () {
  return JSON.parse(open(__ENV.PONTOS || "../data/pontos_paraiba.json"));
});

export const options = {
  vus: Number(__ENV.VUS || 1),
  duration: __ENV.DURATION || "60s",
  summaryTrendStats: ["avg", "med", "p(95)", "p(99)", "max"],
  // Limites folgados só para o resumo trazer as métricas de cada tipo de requisição.
  thresholds: {
    "http_req_duration{fase:medicao}": ["max>=0"],
    "http_req_duration{fase:medicao,name:inicio}": ["max>=0"],
    "http_req_duration{fase:medicao,name:recalculo}": ["max>=0"],
    "http_req_failed{fase:medicao}": ["rate>=0"],
    "http_reqs{fase:medicao}": ["count>=0"],
  },
};

export function setup() {
  return { comeco: Date.now() };
}

function ponto(p) {
  return `${p[0]},${p[1]}`;
}

function marcas(dados, nome) {
  const fase = Date.now() - dados.comeco < AQUECIMENTO_S * 1000 ? "aquecimento" : "medicao";
  return { name: nome, fase: fase };
}

export default function (dados) {
  if (__ITER === 0) {
    // Espalha o começo dos usuários, para as viagens não iniciarem todas juntas.
    sleep(Math.random() * DURACAO_VIAGEM_S);
  }
  const par = pares[Math.floor(Math.random() * pares.length)];
  const inicio = http.post(
    `${BASE_URL}/viagens?origem=${ponto(par.origem)}&destino=${ponto(par.destino)}`,
    null,
    { timeout: TIMEOUT, tags: marcas(dados, "inicio") },
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
      tags: marcas(dados, "recalculo"),
    });
    check(r, { "recalculo 200": (res) => res.status === 200 });
  }

  sleep(PAUSA_S);
  http.del(`${BASE_URL}/viagens/${viagem.viagem}`, null, { timeout: TIMEOUT, tags: marcas(dados, "fim") });
}
