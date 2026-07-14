"""
CLI do FIDC-CDA MVP.

Uso:
    python main.py init-db            # cria o banco e as tabelas
    python main.py import-cadastro    # lê config/fundos_monitorados.csv
    python main.py import-cdas        # importa os CDAs de data/import/
    python main.py enriquecer-cvm     # (opcional) baixa dados públicos da CVM
    python main.py status             # resumo do que está no banco

Depois: streamlit run dashboard/app.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# garante que a raiz do projeto esteja no sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import settings  # noqa: E402
from src.utils.logger import obter_logger  # noqa: E402

log = obter_logger()


def cmd_init_db(_args):
    from src.database import init_db
    settings.garantir_diretorios()
    init_db()
    print(f"[OK] Banco criado/atualizado em: {settings.DB_PATH}")


def cmd_import_cadastro(args):
    from src.importers.cadastro_importer import importar_cadastro
    resumo = importar_cadastro(args.csv)
    print(f"[OK] Cadastro importado: {resumo}")


def cmd_import_cdas(args):
    from src.importers.cda_importer import importar_cdas
    resumos = importar_cdas(args.pasta)
    if not resumos:
        print("[AVISO] Nenhum arquivo encontrado em data/import/.")
        return
    print(f"[OK] {len(resumos)} arquivo(s) processado(s):")
    for r in resumos:
        print(f"   - {r['arquivo']}: {r['status']} "
              f"(cnpjs={r.get('cnpjs', 0)}, fundo={r.get('fundo_cnpj')}, "
              f"comp={r.get('competencia')})")


def cmd_enriquecer_cvm(_args):
    from src.services.cvm_service import enriquecer_cvm
    r = enriquecer_cvm()
    if r.get("status") == "indisponivel":
        print("[!] Não foi possível baixar as bases da CVM (sem internet ou "
              "site fora do ar). O sistema continua funcionando sem os nomes.")
        return
    fontes = r.get("fontes", {})
    print(f"[OK] Enriquecimento CVM concluído.")
    print(f"     Nomes preenchidos: {r.get('ativos', 0)} ativos investidos, "
          f"{r.get('fundos', 0)} fundos.")
    print(f"     Registros lidos: registro_fundo={fontes.get('registro_fundo', 0)}, "
          f"cad_fi={fontes.get('cad_fi', 0)}.")
    if r.get("ativos", 0) == 0 and r.get("fundos", 0) == 0:
        print("     (Nenhum nome novo — pode ser que os CNPJs não estejam nas "
              "bases públicas ou já estivessem preenchidos.)")


def cmd_status(_args):
    from src.database import conectar
    with conectar() as con:
        tabelas = ["gestoras", "fundos", "documentos_cda", "carteiras_cda",
                   "ativos_investidos", "importacoes"]
        print("Resumo do banco:")
        for t in tabelas:
            try:
                n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            except Exception:
                n = "n/d (rode init-db)"
            print(f"   {t:20s}: {n}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="FIDC-CDA MVP — análise de carteiras de FIC FIDC")
    sub = p.add_subparsers(dest="comando", required=True)

    sub.add_parser("init-db").set_defaults(func=cmd_init_db)

    pc = sub.add_parser("import-cadastro")
    pc.add_argument("--csv", type=Path, default=None, help="caminho do CSV de cadastro")
    pc.set_defaults(func=cmd_import_cadastro)

    pi = sub.add_parser("import-cdas")
    pi.add_argument("--pasta", type=Path, default=None, help="pasta de importação")
    pi.set_defaults(func=cmd_import_cdas)

    sub.add_parser("enriquecer-cvm").set_defaults(func=cmd_enriquecer_cvm)
    sub.add_parser("status").set_defaults(func=cmd_status)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
