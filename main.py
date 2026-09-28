"""
This project intentionally has NO script that silently seeds or resets
data on every run — see the incident this avoids: `python main.py`
accidentally wiping inventory before a demo.

Setup is explicit, in order:

    python -m data.generate_synthetic_data   # LLM-generates catalog + policy docs (demo data)
    python -m scripts.ingest_products         # embeds catalog into Chroma (safe to re-run)
    python -m scripts.ingest_policies         # embeds policy docs into Chroma (safe to re-run)
    python -m scripts.seed_demo_data          # ⚠️ resets demo customers + inventory table

Then launch an interface:

    streamlit run interfaces/chat_app.py
    python -m interfaces.voice_app

To wipe the database entirely (drop + recreate all tables):

    python -m scripts.reset_demo_db
"""

if __name__ == "__main__":
    print(__doc__)
