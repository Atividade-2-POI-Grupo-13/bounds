# Configuracoes comuns aos scripts que rodam no hospedeiro.
# Tudo pode ser trocado por variavel de ambiente, ex.: VM=outra-vm experiments/vm_1cpu_1gb.sh

VM="${VM:-vm-poi-exp}"                      # nome da VM do grupo no VirtualBox (a mesma para as 3 aplicacoes)
PORTA="${PORTA:-8080}"                  # hospedeiro 8080 -> VM 8080 (aplicacao)
PORTA_SSH="${PORTA_SSH:-2222}"          # hospedeiro 2222 -> VM 22

# Calibragem na VM do notebook: 100 mil iteracoes = mediana de 54,1 ms.
# 92 mil dao cerca de 50 ms por pedido, ou cerca de 20 pedidos/s por vCPU.
# Em outro hospedeiro (LCC), recalibrar e ajustar aqui.
ITERACOES="${ITERACOES:-92000}"
TAXAS="${TAXAS:-10 30}"                 # pedidos/s: abaixo e acima do que 1 vCPU aguenta

# Senha do usuario osboxes na VM (padrao da imagem). Os scripts a passam ao sudo
# pelo ssh, como no repositorio do Wendell; assim a VM nao precisa de regra de
# sudo sem senha.
SENHA_VM="${SENHA_VM:-osboxes.org}"
