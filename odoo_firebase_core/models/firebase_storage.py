import datetime
import logging

from odoo import models, fields, api
from odoo.tools.safe_eval import safe_eval
from odoo.exceptions import UserError


class OdooFirebaseAttachment(models.Model):
    _name = 'firebase.storage'
    _description = "Firebase: Rule of Attachment"

    name = fields.Char(
        string="Name"
    )
    active = fields.Boolean(
        string="Active",
        default=True
    )
    path = fields.Char(
        string="Path"
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
    is_public = fields.Boolean(
        string="Make public",
        default=False
    )
    expiration = fields.Integer(
        string="Days to URL expiration",
        default=30
    )

    def _get_eval_domain(self):
        self.ensure_one()
        return safe_eval(self.domain, {})

    def cron_sync_attachments(self):
        rules = self.env['firebase.storage'].sudo().search([
            ('active', '=', True),
            ('path', '!=', False),
            ('account_id', '!=', False),
        ])
        rules.force_sync()

    def force_sync(self, res_id=False):
        errors = ""
        for rule in self:
            domain = rule._get_eval_domain()
            if res_id and isinstance(res_id, int):
                domain.append(('res_id', '=', res_id))
            items_without = self.env['ir.attachment'].sudo().search(domain + [
                ('cloud_key', '=', False)
            ], limit=100)
            items_with = self.env['ir.attachment'].sudo().search(domain + [
                ('cloud_key', '!=', False)
            ], order="cloud_last_sync ASC", limit=50)
            items = items_with + items_without
            for item in items:
                try:
                    if item.cloud_last_sync and item.cloud_last_sync > item.write_date:
                        item.write({
                            'cloud_last_sync': fields.Datetime.now()
                        })
                        continue
                    item._send_attachment_to_gcloud(rule)
                    self.env.cr.commit()
                except Exception as e:
                    errors += "El item {} no ha podido subirse. Por razón: {}\n".format(item.id, e)
        if len(errors) > 0:
            raise UserError(errors)
