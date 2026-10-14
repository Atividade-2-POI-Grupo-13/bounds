// Isócronas: cada usuário virtual pede "o que alcanço em MINUTOS minutos" a partir
// de origens aleatórias, uma atrás da outra (pausa opcional de PAUSA_S segundos).
//
// Variáveis: BASE_URL, VUS, DURATION, PONTOS, MINUTOS, PAUSA_S, TIMEOUT, AQUECIMENTO_S
// Exemplo:
//   k6 run -e BASE_URL=http://localhost:8000 -e VUS=5 -e MINUTOS=60 load/alcance.js

import http from "k6/http";
import { check, sleep } from "k6";
import { BASE_URL, TIMEOUT, inicioDoTeste, marcas, opcoes, ponto, sortearPar } from "./comum.js";

const MINUTOS = Number(__ENV.MINUTOS || 60);
const PAUSA_S = Number(__ENV.PAUSA_S || 0);
const AQUECIMENTO_S = Number(__ENV.AQUECIMENTO_S || 10);

export const options = opcoes(["alcance"]);

export function setup() {
  return inicioDoTeste();
}

export default function (dados) {
  const par = sortearPar();
  const r = http.get(`${BASE_URL}/alcance?origem=${ponto(par.origem)}&minutos=${MINUTOS}`, {
    timeout: TIMEOUT,
    tags: marcas(dados, "alcance", AQUECIMENTO_S),
  });
  check(r, { "alcance 200": (res) => res.status === 200 });
  if (PAUSA_S > 0) {
    sleep(PAUSA_S);
  }
}
