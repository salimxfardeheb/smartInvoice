{
    'name': 'SmartInvoice Bridge',
    'version': '16.0.1.0.0',
    'category': 'Accounting',
    'summary': "Bridge d'intégration SmartInvoice ↔ Odoo (XML-RPC).",
    'description': """Bridge minimal d'intégration SmartInvoice → Odoo.

Ce module est un squelette : il déclare les points d'extension qui
servent de contrat d'intégration entre SmartInvoice et Odoo. Il ne
contient pour l'instant aucun modèle ni vue — l'API métier est consommée
via XML-RPC par le client SmartInvoice (``app/odoo``) :

- ``res.partner``           → synchronisation des fournisseurs ;
- ``purchase.order``        → synchronisation des bons de commande ;
- ``purchase.order.line``   → lignes de BC (réf produit, TVA ``tax_ids``) ;
- ``account.move``          → création / réconciliation des Vendor Bills.

L'activation se fait en plaçant ce répertoire dans ``addons_path`` et en
l'installant dans Odoo (``-i smartinvoice_bridge``).
""",
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3'
}