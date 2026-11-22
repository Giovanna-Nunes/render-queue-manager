"""
Midnight Grafite - RenderFarm Server & ED2 TCP Lab
Rodar:
    pip install fastapi uvicorn pydantic
    python -m uvicorn server:app --reload --port 8000
"""
import random
import threading
import time
from typing import Annotated, List, Literal, Tuple

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(title="Midnight Grafite - RenderFarm Server", version="3.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Modelos de Dados

Status = Literal["pendente", "pronto", "erro"]

class Task(BaseModel):
    id: int
    artista: str
    nome: str
    peso: int = Field(ge=1, le=100)
    urgencia: int = Field(ge=1, le=2)  
    status: Status = "pendente"
    criada_em: float = Field(default_factory=time.time)

class NumerosEntrada(BaseModel):
    numeros: List[int]


# "Banco de dados" em memória + Lock de concorrência para Threads

lock = threading.Lock()

db_tarefas: List[Task] = [
    Task(id=101, artista="Giovanna", nome="Personagem_Base.png", peso=45, urgencia=1, status="pronto"),
    Task(id=102, artista="Giovanna", nome="Cenario_Floresta_4K.blend", peso=85, urgencia=1),
    Task(id=103, artista="Rafael", nome="VFX_Particulas.exr", peso=20, urgencia=1),
    Task(id=104, artista="Giovanna", nome="Textura_Corrompida.tga", peso=60, urgencia=1, status="erro"),
]
next_id = 105

def _novo_id() -> int:
    global next_id
    novo = next_id
    next_id += 1
    return novo


# 1. QuickSort para a Fila do Estúdio (Chave: -urgência, peso, id)
Chave = Tuple[int, int, int]

def chave_tarefa(t: Task) -> Chave:
    return (-t.urgencia, t.peso, t.id)

def quick_sort_tarefas(arr: List[Task], contador: List[int]) -> List[Task]:
    if len(arr) <= 1:
        return arr
    
    pivo = arr[random.randrange(len(arr))]
    k_pivo = chave_tarefa(pivo)
    menores, iguais, maiores = [], [], []

    for t in arr:
        contador[0] += 1
        k = chave_tarefa(t)
        if k < k_pivo:
            menores.append(t)
        elif k > k_pivo:
            maiores.append(t)
        else:
            iguais.append(t)

    return quick_sort_tarefas(menores, contador) + iguais + quick_sort_tarefas(maiores, contador)

def montar_fila() -> Tuple[List[Task], int]:
    pendentes = [t for t in db_tarefas if t.status == "pendente"]
    contador = [0]
    ordenadas = quick_sort_tarefas(pendentes, contador)
    return ordenadas, contador[0]


# 2. QuickSort para o Lab de Números Puros
def quick_sort_puro(arr: List[int]) -> Tuple[List[int], List[int]]:
    pivos = []
    def _sort(sub: List[int]) -> List[int]:
        if len(sub) <= 1:
            return sub
        pivo = sub[len(sub) // 2]  # Escolha do pivô central
        pivos.append(pivo)
        menores = [x for x in sub if x < pivo]
        iguais = [x for x in sub if x == pivo]
        maiores = [x for x in sub if x > pivo]
        return _sort(menores) + iguais + _sort(maiores)
    
    ordenado = _sort(arr)
    return ordenado, pivos


def _buscar(task_id: int) -> Task:
    for t in db_tarefas:
        if t.id == task_id:
            return t
    raise HTTPException(status_code=404, detail="Tarefa não encontrada")




@app.get("/api/tarefas")
def obter_tarefas():
    with lock:
        return {"tarefas": [t.model_dump() for t in db_tarefas]}

@app.post("/api/tarefas")
def criar_tarefa(
    nome: Annotated[str, Query(min_length=1, max_length=120)],
    peso: Annotated[int, Query(ge=1, le=100)],
    urgencia: Annotated[int, Query(ge=1, le=2)],
    artista: Annotated[str, Query(min_length=1, max_length=60)] = "Giovanna",
):
    with lock:
        nova = Task(id=_novo_id(), artista=artista, nome=nome.strip(), peso=peso, urgencia=urgencia)
        db_tarefas.append(nova)
        return {"message": "Tarefa enfileirada com sucesso!", "tarefa": nova.model_dump()}

@app.patch("/api/tarefas/{task_id}/priorizar")
def priorizar_tarefa(task_id: int):
    with lock:
        t = _buscar(task_id)
        if t.status != "pendente":
            raise HTTPException(status_code=400, detail="Só é possível priorizar tarefas pendentes")
        t.urgencia = 2
        return {"message": f"Tarefa #{task_id} promovida para alta prioridade."}

@app.post("/api/tarefas/{task_id}/reprocessar")
def reprocessar_tarefa(task_id: int):
    with lock:
        t = _buscar(task_id)
        if t.status != "erro":
            raise HTTPException(status_code=400, detail="Só tarefas com erro podem ser reprocessadas")
        t.status = "pendente"
        return {"message": f"Tarefa #{task_id} retornou para a fila."}

@app.post("/api/servidor/processar")
def processar_proximo():
    with lock:
        ordenadas, _ = montar_fila()
        if not ordenadas:
            raise HTTPException(status_code=400, detail="Fila vazia!")

        alvo = ordenadas[0]
       
        alvo.status = "pronto" if random.random() > 0.2 else "erro"
        return {
            "message": f"Tarefa #{alvo.id} processada.",
            "tarefa": alvo.model_dump(),
        }

@app.get("/api/fila")
def obter_fila():
    """Retorna a fila ordenada pelo QuickSort do servidor para o painel visual."""
    with lock:
        ordenadas, comparacoes = montar_fila()
        return {
            "algoritmo": "QuickSort",
            "total": len(ordenadas),
            "comparacoes": comparacoes,
            "fila": [
                {"posicao": i + 1, **t.model_dump()} for i, t in enumerate(ordenadas)
            ],
        }

@app.post("/api/sockets/ordenar")
def ordenar_numeros_tcp(payload: NumerosEntrada):
    """
    Atende diretamente ao requisito principal do trabalho de Estrutura de Dados 2:
    Recebe números inteiros, aplica o QuickSort e devolve o vetor ordenado e pivôs[cite: 9, 10].
    """
    if not payload.numeros:
        raise HTTPException(status_code=400, detail="Nenhum número foi enviado.")
    
    ordenados, pivos = quick_sort_puro(payload.numeros)
    return {
        "recebidos": payload.numeros,
        "ordenados": ordenados,
        "pivos_utilizados": pivos,
        "algoritmo": "QuickSort (Particionamento por Pivô)"
    }