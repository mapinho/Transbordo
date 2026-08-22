from django.test import TestCase

from apps.core.models import Cooperativa


class CooperativaTests(TestCase):
    def test_criacao_com_campos_minimos(self):
        cooperativa = Cooperativa.objects.create(nome='Cooperativa Teste', slug='cooperativa-teste')

        self.assertTrue(cooperativa.ativo)
        self.assertIsNone(cooperativa.dias_janela_safra_padrao)

    def test_str_retorna_nome(self):
        cooperativa = Cooperativa.objects.create(nome='Cooperativa Teste', slug='cooperativa-teste')

        self.assertEqual(str(cooperativa), 'Cooperativa Teste')

    def test_slug_e_unico(self):
        Cooperativa.objects.create(nome='Primeira', slug='mesma-slug')

        with self.assertRaises(Exception):
            Cooperativa.objects.create(nome='Segunda', slug='mesma-slug')
