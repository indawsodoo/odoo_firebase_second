# -*- coding: utf-8 -*-
{
    'name': 'Firebase Odoo Connector',
    "category": "Tools",
    "website": "https://melkart.io/",
    "author": "Melkart",
    "license": "Other proprietary",
    'data': [
        'security/ir.model.access.csv',
        'data/cron.xml',
        'views/firebase_account.xml',
        'views/firebase_rule.xml',
        'views/firebase_auth.xml',
        'views/firebase_storage.xml',
        'views/firebase_log.xml',
        'views/menu.xml',
    ],
    # only loaded in demonstration mode
    'depends': ['mail'],
    'demo': [],
    'qweb': [],
    'application': True,
    "installable": True,
    'summary': """Configuración de Odoo con Firebase""",
    'description': """
       Configuración de Odoo con Firebase 
    """,
    "images": [
        'static/description/main.png'
    ],
    "currency": "EUR",
    "price": 99.90,
}
