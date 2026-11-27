"""Section « Prochains rendez-vous » des fiches produits : événements à venir de l'équipe du produit."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from django.utils.text import slugify
from wagtail.models import Site

from blog.models import Category
from events.models import EventEntryPage, EventsIndexPage
from fabrique.models import EtiquettesEvenement, ProduitPage, ProduitsIndexPage


class AgendaProduitTests(TestCase):
    def setUp(self):
        root = Site.objects.get(is_default_site=True).root_page
        self.agenda = EventsIndexPage(title="Agenda", slug="agenda")
        root.add_child(instance=self.agenda)
        self.agenda.save_revision().publish()
        catalogue = ProduitsIndexPage(title="Produits", slug="produits")
        root.add_child(instance=catalogue)
        catalogue.save_revision().publish()
        # Catégorie des actualités du RNB, sous l'adresse que lui donne la synchronisation des actus.
        rnb = Category.objects.create(name="Référentiel National des Bâtiments", slug="referentiel-national-du-batiment")
        self.produit = ProduitPage(
            title="Référentiel National des Bâtiments", slug="rnb", betagouv_id="bat-id", categorie_actualites=rnb
        )
        catalogue.add_child(instance=self.produit)
        self.produit.save_revision().publish()
        self.maintenant = timezone.now()

    def evenement(self, titre, dans_jours, equipes, type="", duree_jours=0, publie=True):
        debut = self.maintenant + timedelta(days=dans_jours)
        page = EventEntryPage(
            title=titre, slug=slugify(titre), event_date_start=debut,
            event_date_end=debut + timedelta(days=duree_jours, hours=1),
        )  # fmt: skip
        page.tags.set([t for t in [type, *equipes] if t])
        self.agenda.add_child(instance=page)
        if publie:
            page.save_revision().publish()
        else:
            page.unpublish()
        EtiquettesEvenement.objects.create(page=page, type=type, equipes=list(equipes))
        return page

    def contenu(self):
        reponse = self.client.get(self.produit.url)
        self.assertEqual(reponse.status_code, 200)
        return reponse.content.decode()

    def test_rendez_vous_a_venir_de_l_equipe(self):
        self.evenement("GT CNIG Bâtiment", 3, ["RNB"], type="Groupe de travail")
        self.evenement("Comité RNB", 1, ["RNB", "Fabrique de la donnée territoriale"], type="Comité d'investissement")
        self.evenement("Atelier en cours", -2, ["RNB"], duree_jours=4)  # commencé, pas fini
        self.evenement("Démo passée", -10, ["RNB"])
        self.evenement("Hébergement Panoramax", 2, ["Panoramax"])
        self.evenement("Brouillon RNB", 5, ["RNB"], publie=False)

        agenda = self.produit.agenda()
        self.assertEqual(
            [e.title for e in agenda["evenements"]], ["Atelier en cours", "Comité RNB", "GT CNIG Bâtiment"]
        )
        self.assertEqual(agenda["tout"], "/agenda/?tag=rnb")

        contenu = self.contenu()
        self.assertIn("<h2>Prochains rendez-vous</h2>", contenu)
        self.assertIn('href="/agenda/comite-rnb/"', contenu)
        self.assertIn("Comité d&#x27;investissement", contenu)
        self.assertNotIn("Hébergement Panoramax", contenu)
        self.assertIn('href="/agenda/?tag=rnb">Tout l\'agenda du produit</a>', contenu)

    def test_limite_a_quatre(self):
        for i in range(6):
            self.evenement(f"Rendez-vous {i}", i + 1, ["RNB"])
        self.assertEqual(
            [e.title for e in self.produit.agenda()["evenements"]], [f"Rendez-vous {i}" for i in range(4)]
        )

    def test_pas_de_section_sans_rendez_vous(self):
        self.evenement("Démo passée", -10, ["RNB"])
        self.evenement("Hébergement Panoramax", 2, ["Panoramax"])
        self.assertIsNone(self.produit.agenda())
        self.assertNotIn("Prochains rendez-vous", self.contenu())

    def test_equipe_reconnue_sans_categorie(self):
        self.produit.categorie_actualites = None
        self.produit.title = "Panoramax"
        self.produit.save()
        self.evenement("Hébergement Panoramax", 2, ["Panoramax"])
        self.assertEqual([e.title for e in self.produit.agenda()["evenements"]], ["Hébergement Panoramax"])
        self.assertFalse(self.produit.est_son_equipe("RNB"))
