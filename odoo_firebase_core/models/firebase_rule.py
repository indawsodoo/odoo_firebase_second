import datetime
import unicodedata

from odoo import models, fields, api, exceptions
from odoo.tools import safe_eval
import logging


def unaccent_string(txt):
    return unicodedata.normalize('NFD', txt).encode('ascii', 'ignore').decode('utf-8')


def get_item_dict(self, rule, item, level=0):
    if rule.result_type == 'method' and hasattr(item, rule.method):
        return getattr(item, rule.method)()
    dict_value = {
        'search_terms': []
    }
    fields_dict = [
        ('model_id.model', '=', item._name),
        ('ttype', '!=', 'binary')
    ]
    if level == 0:
        if rule.result_type == 'norel':
            fields_dict.append(('ttype', 'not in', ['many2one', 'one2many', 'many2many']))
        elif rule.result_type == 'notree':
            fields_dict.append(('ttype', 'not in', ['one2many', 'many2many']))
        elif rule.result_type == 'custom':
            fields_dict.append(('id', 'in', rule.custom_field_ids.ids))
    else:
        fields_dict.append(('ttype', 'not in', ['one2many', 'many2many']))
    fields_search = self.env['ir.model.fields'].sudo().search(fields_dict)
    for field in fields_search:
        value = getattr(item, field.name, False)
        if field.ttype == 'many2one':
            if not value:
                dict_value[field.name] = {
                    'id': False,
                    'name': ""
                }
            else:
                rec_name = value._rec_name if value._rec_name else "name"
                sub_value = getattr(value, rec_name, False) if value else ""
                dict_value[field.name] = {
                    'id': value.id if value else False,
                    'name': sub_value if isinstance(sub_value, str) else ""
                }
            if field.relation == 'ir.attachment':
                dict_value[field.name]['url'] = getattr(value, 'url', False) if value else ""
        elif field.ttype in ['one2many', 'many2many']:
            if level == 2:
                continue
            key_map = "map_{}".format(field.name)
            dict_value[key_map] = {}
            dict_value[field.name] = []
            for subitem in getattr(item, field.name, []):
                dict_value[key_map][str(subitem.id)] = True
                dict_value[field.name].append(get_item_dict(self, rule, subitem, level + 1))
        elif field.ttype in ['date']:
            if not value:
                dict_value[field.name] = False
            else:
                dict_value[field.name] = str(value)
        elif field.ttype in ['datetime']:
            if not value:
                dict_value[field.name] = False
            elif self.env.context.get('force_string', False):
                dict_value[field.name] = str(value)
            else:
                dict_value[field.name] = value
        elif field.ttype in ['boolean']:
            dict_value[field.name] = bool(value)
        elif field.ttype in ['integer']:
            dict_value[field.name] = int(value)
        elif field.ttype in ['monetary', 'float']:
            dict_value[field.name] = float(value)
        else:
            dict_value[field.name] = str(value) if value else ""

        if field.id in rule.search_field_ids.ids:
            words = str(value).lower().split(' ')
            full_words = ""
            for word in words:
                part = ""
                for letter in word:
                    part += unaccent_string(letter)
                    full_words += unaccent_string(letter)
                    dict_value['search_terms'].append(part)
                    dict_value['search_terms'].append(full_words)
                dict_value['search_terms'].append(unaccent_string(word))
                full_words += " "
            dict_value['search_terms'].append(unaccent_string(str(value)))
    return dict_value


def logic_write(self, ids, account=False, rule=False, delete=False, operation=False):
    if not rule:
        rules = self.env['firebase.rule'].sudo().search([
            ('model_name', '=', self._name),
        ])
    else:
        rules = [rule]
    for rule in rules:
        for item in self:
            dict_search = rule._get_eval_domain()
            dict_search.append(('id', '=', item.id))
            count_record = self.sudo().search_count(dict_search)
            if count_record <= 0:
                continue
            dict_value = get_item_dict(self, rule, item)
            log = self.env['firebase.log'].sudo().create({
                'model_name': item._name,
                'path_name': rule.path_firebase,
                'res_id': item.id,
                'path_id': str(item.id),
                'operation_type': operation,
                'is_processed': False,
                'data': dict_value
            })
            if not account:
                if delete:
                    rule.account_id.delete_firebase_object(rule.path_firebase, item.id)
                else:
                    rule.account_id.update_firebase_object(rule.path_firebase, dict_value)
            else:
                if delete:
                    account.delete_firebase_object(rule.path_firebase, item.id)
                else:
                    account.update_firebase_object(rule.path_firebase, dict_value)
            log.write({
                'is_processed': True,
                'date_processed': fields.Datetime.now()
            })


class OdooFirebaseConfigLine(models.Model):
    _name = 'firebase.rule'
    _description = "Firebase: Rule of Sync"

    active = fields.Boolean(
        string="Active",
        default=True
    )
    model_id = fields.Many2one(
        comodel_name='ir.model',
        string='Model',
        required=True,
        ondelete="cascade"
    )
    model_name = fields.Char(
        string="Model Name",
        related="model_id.model",
    )
    path_firebase = fields.Char(
        string='Firebase Path',
        help='Path of firebase database where you want to write odoo info.',
        required=True
    )
    allow_create = fields.Boolean(
        string='Allow Create',
        default=True
    )
    allow_update = fields.Boolean(
        string='Allow Write',
        default=True
    )
    allow_delete = fields.Boolean(
        string='Allow Delete',
        default=True
    )
    account_id = fields.Many2one(
        comodel_name='firebase.account',
        string='Account'
    )
    domain = fields.Text(
        string="Domain",
        default='[]',
        required=False
    )
    result_type = fields.Selection(
        string="Fields to Migrate",
        selection=[
            ('method', 'Method'),
            ('norel', 'All fields except relational fields'),
            ('notree', 'All fields except relational multi-level (One2many and Many2many)'),
            ('custom', 'Add fields that you want to send'),
            ('all', 'All Fields')
        ], default="all"
    )
    method = fields.Char(
        string="Custom Method"
    )
    custom_field_ids = fields.Many2many(
        string="Custom Fields",
        comodel_name="ir.model.fields",
        domain="[('model_id','=',model_id)]"
    )
    search_field_ids = fields.Many2many(
        string="Search Fields",
        comodel_name="ir.model.fields",
        domain="[('model_id','=',model_id),('ttype','in',['char','html','selection','text'])]",
        relation="firebase_rule_search_field_ids",
        column1="rule_id", column2="field_id"
    )

    def _get_eval_domain(self):
        self.ensure_one()
        return safe_eval.safe_eval(self.domain, {
            'datetime': safe_eval.datetime,
            'dateutil': safe_eval.dateutil,
            'time': safe_eval.time,
            'uid': self.env.uid,
            'user': self.env.user,
        })

    def _register_hook(self):
        """Get all rules and apply them to log method calls."""
        super(OdooFirebaseConfigLine, self)._register_hook()
        if not self:
            self = self.search([('path_firebase', '!=', False)])
        return self._patch_methods()

    def _patch_methods(self):
        """Patch ORM methods of models defined in rules to log their calls."""
        updated = False
        for rule in self:
            if not rule.active:
                continue
            if not self.pool.get(rule.model_id.model):
                # ignore rules for models not loadable currently
                continue
            model_model = self.env[rule.model_id.model]
            setattr(type(model_model), 'firebase_active', True)
            # CRUD
            #   -> create
            check_attr = 'firebase_ruled_create'
            if getattr(rule, 'allow_create') and not hasattr(model_model, check_attr):
                model_model._patch_method('create', rule._make_create())
                setattr(type(model_model), check_attr, True)
                updated = True
            #   -> write
            check_attr = 'firebase_ruled_write'
            if getattr(rule, 'allow_update') and not hasattr(model_model, check_attr):
                model_model._patch_method('write', rule._make_write())
                setattr(type(model_model), check_attr, True)
                updated = True
            #   -> unlink
            check_attr = 'firebase_ruled_unlink'
            if getattr(rule, 'allow_delete') and not hasattr(model_model, check_attr):
                model_model._patch_method('unlink', rule._make_unlink())
                setattr(type(model_model), check_attr, True)
                updated = True
        return updated

    def _make_create(self):
        """Instanciate a create method that log its calls."""
        self.ensure_one()

        @api.model
        @api.returns('self', lambda value: value.id)
        def create_full(self, vals, **kwargs):
            self = self.with_context()
            new_record = create_full.origin(self, vals, **kwargs)
            if new_record.firebase_active:
                try:
                    logic_write(new_record, [new_record.id], operation='create')
                except:
                    pass
            return new_record

        return create_full

    def _make_write(self):
        """Instanciate a write method that log its calls."""
        self.ensure_one()

        def write_full(self, vals, **kwargs):
            self = self.with_context()
            result = write_full.origin(self, vals, **kwargs)
            if self.firebase_active:
                try:
                    logic_write(self, self.ids, operation='write')
                except:
                    pass
            return result

        return write_full

    def _make_unlink(self):
        """Instanciate an unlink method that log its calls."""
        self.ensure_one()

        def unlink_full(self, **kwargs):
            self = self.with_context()
            if self.firebase_active:
                try:
                    logic_write(self, self.ids, delete=True, operation='unlink')
                except:
                    pass
            return unlink_full.origin(self, **kwargs)

        return unlink_full

    def force_sync(self):
        self.ensure_one()
        if not self.model_id:
            raise exceptions.UserError("Es obligatorio tener un modelo")
        items = self.env[self.model_id.model].sudo().search(self._get_eval_domain(), order="id DESC")
        if not items:
            raise exceptions.UserError("No hay items que migrar")
        logic_write(items, items.ids, account=self.account_id, rule=self, operation="write")
