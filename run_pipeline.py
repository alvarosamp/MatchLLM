from pathlib import Path
from core.Pipeline.pipeline import MatchPipeline

if __name__ == "__main__":

    BASE = Path(__file__).resolve().parent

    edital_path = BASE / "data/editais/EDITAL_DO_PREGAO_ELETRONICO_N_242025__MATERIAL_DE_INFORMATICA_anx7532518935684159076.pdf"
    produto_path = BASE / "data/produtos/Produto36334IdArquivo15589.pdf"

    pipeline = MatchPipeline(
        top_k_edital_chunks=10,
        enable_justification=True,
        llm_model=None,  # usa LLM_MODEL do env
    )

    result = pipeline.run(str(edital_path), str(produto_path))
    pipeline.save_result(result, "resultado_final.json")

    print("Status geral:", result["score"]["status_geral"])
    print("Score (%):", result["score"]["score_percent"])
    print(
        "Obrigatórios atendidos:",
        f'{result["score"]["obrigatorios_atende"]}/{result["score"]["obrigatorios_total"]}'
    )
    print("Arquivo gerado: resultado_final.json")
