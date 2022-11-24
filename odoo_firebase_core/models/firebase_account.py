import base64
import pathlib
import datetime
import firebase_admin
import sys
import json
import logging
from firebase_admin import credentials, firestore

from odoo import models, fields, api, exceptions, _
from odoo.tools.safe_eval import safe_eval

apps = {}


class OdooFirebase(models.Model):
    _name = 'firebase.account'
    _description = 'Firebase: Accounts'

    name = fields.Char(
        string='Name'
    )
    account_firebase = fields.Char(
        string='Account',
        required=True
    )
    bucket_url = fields.Char(
        string="Bucket Storage"
    )
    file_firebase = fields.Binary(
        string='Firebase Key File'
    )
    auth = fields.Selection(
        string="Sync. Auth",
        selection=[
            ('off', 'Off'),
            ('partner', 'Sync All Partners'),
        ], default="off",
    )
    auth_domain = fields.Text(
        string="Auth Domain",
        default="[]"
    )
    auth_field_user = fields.Many2one(
        string="Field for default user",
        comodel_name="ir.model.fields",
        domain="[('model_id.model','=','res.partner')]"
    )
    auth_field_user_sufix = fields.Char(
        string="Sufix for concatenate with user field"
    )
    auth_field_pass = fields.Many2one(
        string="Field for default pass",
        comodel_name="ir.model.fields",
        domain="[('model_id.model','=','res.partner')]"
    )
    rule_ids = fields.One2many(
        comodel_name='firebase.rule',
        inverse_name='account_id',
        string='Paths to Sync.'
    )
    storage_rule_ids = fields.One2many(
        comodel_name='firebase.storage',
        inverse_name='account_id',
        string='Storage Path to Sync.'
    )

    def _get_auth_eval_domain(self):
        self.ensure_one()
        return safe_eval(self.auth_domain, {})

    @api.model
    def _get_local_filename(self):
        actual_route = pathlib.Path(__file__).parent.parent.absolute()
        return "{}/credentials/credentials_{}.json".format(actual_route, self.account_firebase)

    @api.model
    def _get_app(self):
        if self.id in apps:
            return apps[self.id]
        credential_file = json.loads(base64.b64decode(self.file_firebase).decode('utf-8'))
        cred = credentials.Certificate(credential_file)
        if self.bucket_url:
            apps[self.id] = firebase_admin.initialize_app(cred, {
                'storageBucket': self.bucket_url
            })
        else:
            apps[self.id] = firebase_admin.initialize_app(cred)
        if self.id in apps:
            return apps[self.id]
        else:
            return False

    @api.model
    def create_firebase_object(self, path, vals):
        try:
            app = self._get_app()
            store = firestore.client(app)
            store.collection(path).document(str(vals['id'])).set(vals)
        except ValueError:
            raise exceptions.UserError(_("""
                   Path has not a valid format.\n
                   Check path can not has any symbol first (like slash /)
               """))

    @api.model
    def update_firebase_object(self, path, vals, force_update=False):
        try:
            app = self._get_app()
            store = firestore.client(app)
            try:
                if force_update:
                    store.collection(path).document(str(vals['id'])).update(vals)
                else:
                    store.collection(path).document(str(vals['id'])).set(vals)
            except:
                ref = store.collection(path).document(str(vals['id']))
                for key in vals:
                    val_dict = {}
                    val_dict[key] = vals[key]
                    try:
                        ref.update(val_dict)
                    except:
                        logging.info(sys.getsizeof(vals))
                        logging.info(sys.getsizeof(vals[key]))
                        logging.info(vals)
        except ValueError:
            raise exceptions.UserError(_("""
                   Path has not a valid format.\n
                   Check path can not has any symbol first (like slash /)
               """))

    @api.model
    def delete_firebase_object(self, path, id):
        try:
            app = self._get_app()
            store = firestore.client(app)
            store.collection(path).document(str(id)).delete()
        except ValueError:
            raise exceptions.UserError(_("""
                   Path has not a valid format.\n
                   Check path can not has any symbol first (like slash /)
               """))

    @api.model
    def delete_firebase_collection(self, path):
        try:
            app = self._get_app()
            store = firestore.client(app)
            coll_ref = store.collection(path)
            docs = coll_ref.limit(500).stream()
            deleted = 0

            for doc in docs:
                doc.reference.delete()
                deleted = deleted + 1

        except ValueError as e:
            raise exceptions.UserError(_("""
                   Path has not a valid format.\n
                   Check path can not has any symbol first (like slash /)
               """))
    def cron_import_data(self, reset=False):
        accounts = self.env[self._name].sudo().search([])
        for ac in accounts:
            if reset:
                ac._reset_odoo_import()
            ac._import_data()

    def _import_data(self):
        app = self._get_app()
        collection = '_odoo_import'
        store = firestore.client(app)
        query_ref = store.collection(collection).where(
            'in_progress', '==', False
        ).where(
            'is_ready', '==', True
        ).where(
            'finished', '==', False
        ).limit(10)
        for doc in query_ref.stream():
            store.collection(collection).document(doc.id).update({
                'in_progress': True
            })
            dict = doc.to_dict()
            update_data = {
                'in_progress': False,
                'finished': True,
            }
            try:
                if dict['type'] == 'create':
                    new_obj = self._import_create(dict)
                    update_data['res_id'] = new_obj.id
                elif dict['type'] == 'write':
                    self._import_write(dict)
                elif dict['type'] == 'delete':
                    self._import_delete(dict)
                store.collection(collection).document(doc.id).update(update_data)
                self.env.cr.commit()
            except Exception as e:
                self.env.cr.rollback()
                store.collection(collection).document(doc.id).update({
                    'in_progress': False,
                    'error': True,
                    'error_message': str(e)
                })

    def _import_create(self, data):
        model_obj = self.env[data['res_model']]
        dict = self._merge_data(data)
        obj = model_obj.sudo().create(dict)
        if 'after_execute' in data and 'method' in data['after_execute']:
            if 'model' in data['after_execute']:
                obj = self.env[data['after_execute']['model']].sudo()
            val = getattr(obj, data['after_execute']['method'])
            if val:
                val()
        return obj

    def _import_write(self, data):
        model_obj = self.env[data['res_model']]
        obj = model_obj.sudo().browse(int(data['res_id']))
        dict = self._merge_data(data)
        if obj:
            obj.write(dict)
            if 'after_execute' in data and 'method' in data['after_execute']:
                if 'model' in data['after_execute']:
                    obj = self.env[data['after_execute']['model']].sudo()
                val = getattr(obj, data['after_execute']['method'])
                if val:
                    val()
        return {}

    def _import_delete(self, data):
        model_obj = self.env[data['res_model']]
        obj = model_obj.sudo().browse(int(data['res_id']))
        if obj:
            obj.unlink()
            if 'after_execute' in data and 'method' in data['after_execute']:
                obj = self.env[data['after_execute']['model']].sudo()
                val = getattr(obj, data['after_execute']['method'])
                if val:
                    val()
        return {}

    def _merge_data(self, data):
        if 'data' in data:
            dict = data['data']
        else:
            dict = {}
        if 'related_data' in data:
            for rel in data['related_data']:
                kfield = rel['field']
                dict[kfield] = []
                if rel['type'] == 'set':
                    dict[kfield].append((6, 0, [int(val) for val in rel['value']]))
                elif rel['type'] == 'add':
                    for val in rel['value']:
                        dict[kfield].append((4, int(val)))
                elif rel['type'] == 'new':
                    for val in rel['value']:
                        dict[kfield].append((0, 0, val))
                elif rel['type'] == 'create':
                    for val in rel['value']:
                        dict[kfield].append((0, 0, val))
                elif rel['type'] == 'hot-create':
                    obj = self.env[rel['res_model']].sudo()
                    item = obj.search([
                        (rel['search_by'], 'like', rel['data'][rel['search_by']])
                    ], limit=1)
                    if not item:
                        item = obj.create(rel['data'])
                    dict[kfield] = item.id
                elif rel['type'] == 'if-exists':
                    obj = self.env[rel['res_model']].sudo()
                    item = obj.search([
                        (rel['search_key'], 'like', rel['search_value'])
                    ], limit=1)
                    if item:
                        dict[kfield] = item.id
        return dict

    def _reset_odoo_import(self):
        app = self._get_app()
        collection = '_odoo_import'
        store = firestore.client(app)
        query_ref = store.collection(collection).where(
            'in_progress', '==', True
        ).where(
            'is_ready', '==', True
        ).where(
            'finished', '==', False
        )
        for doc in query_ref.stream():
            store.collection(collection).document(doc.id).update({
                'in_progress': False
            })
