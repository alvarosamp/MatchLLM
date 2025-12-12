from pydantic import BaseModel

class Produto(BaseModel):
    """
    Podemos implementar mais coisas depois
    As que defini agora sao para testes iniciais
    """
    nome : str
    atributos : dict
    