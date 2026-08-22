from django.db import connection, models
from django.test import TestCase
from django.test.utils import isolate_apps

from apps.core.models import Cooperativa
from apps.core.tenancy import (
    CooperativaScopedModel,
    definir_cooperativa_atual,
    resetar_cooperativa_atual,
)


class TenantManagerIsolationTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._isolation = isolate_apps('apps.core')
        isolated_apps = cls._isolation.enable()
        cls.addClassCleanup(cls._isolation.disable)
        # Item.cooperativa (herdado de CooperativaScopedModel) referencia
        # 'core.Cooperativa' por string; o registry isolado criado por
        # isolate_apps() não reimporta modelos já carregados no registry real,
        # então é preciso registrar Cooperativa manualmente para a FK resolver.
        isolated_apps.all_models['core']['cooperativa'] = Cooperativa

        class Item(CooperativaScopedModel):
            nome = models.CharField(max_length=100)

            class Meta:
                app_label = 'core'

        cls.Item = Item
        with connection.schema_editor() as editor:
            editor.create_model(cls.Item)

    @classmethod
    def tearDownClass(cls):
        with connection.schema_editor() as editor:
            editor.delete_model(cls.Item)
        super().tearDownClass()

    def setUp(self):
        self.coop_a = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.coop_b = Cooperativa.objects.create(nome='Coop B', slug='coop-b')
        self.Item.all_cooperativas.create(cooperativa=self.coop_a, nome='Item A')
        self.Item.all_cooperativas.create(cooperativa=self.coop_b, nome='Item B')

    def test_scoped_manager_returns_empty_without_current_cooperativa(self):
        self.assertEqual(list(self.Item.objects.all()), [])

    def test_scoped_manager_filters_by_current_cooperativa(self):
        token = definir_cooperativa_atual(self.coop_a.id)
        try:
            nomes = list(self.Item.objects.values_list('nome', flat=True))
        finally:
            resetar_cooperativa_atual(token)
        self.assertEqual(nomes, ['Item A'])

    def test_scoped_manager_never_leaks_other_cooperativa(self):
        token = definir_cooperativa_atual(self.coop_a.id)
        try:
            vazou = self.Item.objects.filter(nome='Item B').exists()
        finally:
            resetar_cooperativa_atual(token)
        self.assertFalse(vazou)

    def test_all_cooperativas_manager_bypasses_scope(self):
        self.assertEqual(self.Item.all_cooperativas.count(), 2)
