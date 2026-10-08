// Partes comuns aos scripts de carga: pares de teste, aquecimento e opções do resumo.
//
// As requisições dos primeiros AQUECIMENTO_S segundos levam a marca fase=aquecimento
// e ficam fora das métricas de medição (fase=medicao).

import { SharedArray } from "k6/data";

export const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
export const TIMEOUT = __ENV.TIMEOUT || "30s";

export const pares = new SharedArray("pares", function () {
  return JSON.parse(open(__ENV.PONTOS || "../data/pontos_paraiba.json"));
});

// nomes: tipos de requisição do script, cada um com p95 próprio no resumo.
export function opcoes(nomes) {
  const limites = {
    // Limites folgados: só fazem o resumo trazer as métricas da fase de medição.
    "http_req_duration{fase:medicao}": ["max>=0"],
    "http_req_failed{fase:medicao}": ["rate>=0"],
    "http_reqs{fase:medicao}": ["count>=0"],
  };
  for (const nome of nomes) {
    limites[`http_req_duration{fase:medicao,name:${nome}}`] = ["max>=0"];
  }
  return {
    vus: Number(__ENV.VUS || 1),
    duration: __ENV.DURATION || "60s",
    summaryTrendStats: ["avg", "med", "p(95)", "p(99)", "max"],
    thresholds: limites,
  };
}

export function inicioDoTeste() {
  return { comeco: Date.now() };
}

export function marcas(dados, nome, aquecimentoS) {
  const fase = Date.now() - dados.comeco < aquecimentoS * 1000 ? "aquecimento" : "medicao";
  return { name: nome, fase: fase };
}

export function sortearPar() {
  return pares[Math.floor(Math.random() * pares.length)];
}

export function ponto(p) {
  return `${p[0]},${p[1]}`;
}
