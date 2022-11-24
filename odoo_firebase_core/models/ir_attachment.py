import base64
import logging
from datetime import datetime, timedelta

from firebase_admin import storage
from odoo import models, fields, api


class OdooFireIrAttachment(models.Model):
    _inherit = "ir.attachment"

    cloud_key = fields.Char(
        string="Cloud key",
        copy=False
    )
    cloud_path = fields.Char(
        string="Cloud path",
        copy=False
    )
    cloud_url = fields.Char(
        string="Cloud URL",
        copy=False
    )
    cloud_last_sync = fields.Datetime(
        string="Cloud Last Sync",
        copy=False
    )

    def _send_attachment_to_gcloud(self, rule):
        self.ensure_one()
        app = rule.account_id._get_app()
        bucket = storage.bucket(name=rule.account_id.bucket_url, app=app)
        url = False
        if self.cloud_key and self.cloud_path:
            res = bucket.get_blob(self.cloud_path)
        else:
            name = "{}/{}-{}".format(
                rule.path if rule.path else "",
                str(self.id),
                self.store_fname
            )
            content = base64.urlsafe_b64decode(self.datas)
            res = bucket.blob(name)
            res.upload_from_string(
                data=content,
                content_type=self.mimetype
            )
        if rule.is_public:
            res.make_public()
        else:
            current_date = datetime.today()
            url = res.generate_signed_url(
                expiration=current_date + timedelta(days=rule.expiration)
            )
        if res:
            self.write({
                'cloud_key': res.id,
                'cloud_path': res.name,
                'cloud_url': url if url else res.public_url,
                'cloud_last_sync': fields.Datetime.now()
            })
        return res

    @api.model
    def _find_rule_from_storage(self):
        self.ensure_one()
        rules = self.env['firebase.storage'].sudo().search([])
        for rule in rules:
            filter = rule._get_eval_domain()
            filter.append(('id', '=', self.id))
            num = self.env[self._name].sudo().search_count(filter)
            if num > 0:
                return rule
        return False

    def unlink(self):
        for att in self:
            if att.cloud_key and att.cloud_path:
                rule = att._find_rule_from_storage()
                if not rule:
                    return None
                app = rule.account_id._get_app()
                bucket = storage.bucket(name=rule.account_id.bucket_url, app=app)
                res = bucket.get_blob(att.cloud_path)
                if res:
                    res.delete()
        return super(OdooFireIrAttachment, self).unlink()
