from pathlib import Path

from django.conf import settings
from django.test import TestCase

REMOVIDOS = [
    'GEMINI.md', '.gemini/settings.json',
    'code-reviewer/SKILL.md', 'code-reviewer/scripts/review.py',
    'INSTRUCOES_MCP.md', 'toolspec.json',
    'conductor/ai-assistant-plan.md', 'conductor/mcp-server.md',
    'Relatorio_Revisao_Codigo_Fase1.md',
    'analise_mineiros.py', 'Relatorio_Analise_Impacto_Vendas_Mineiros.md',
    'Cenário de Simulação.txt', 'Especificação Transbordo.txt',
]


class CleanupGuardTests(TestCase):
    def test_cruft_is_gone(self):
        root = Path(settings.BASE_DIR)
        ainda_existem = [p for p in REMOVIDOS if (root / p).exists()]
        self.assertEqual(ainda_existem, [], f'ainda presentes: {ainda_existem}')

    def test_no_dangling_references_in_kept_docs(self):
        root = Path(settings.BASE_DIR)
        nomes = ['GEMINI.md', 'INSTRUCOES_MCP.md', 'toolspec.json',
                 'Relatorio_Revisao_Codigo_Fase1.md', 'conductor/']
        for doc in ['CLAUDE.md', 'README.md']:
            texto = (root / doc).read_text(encoding='utf-8')
            hits = [n for n in nomes if n in texto]
            self.assertEqual(hits, [], f'{doc} ainda referencia: {hits}')
