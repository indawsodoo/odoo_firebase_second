from odoo import models, fields
from firebase_admin import auth


class FirebaseAuth(models.Model):
    _name = "firebase.auth"
    _description = "Firebase: Authentication"

    _sql_constraints = [
        ('ac_partner_uniq',
         'unique (account_id,partner_id)',
         'A partner could be defined only one time on same account.')
    ]

    account_id = fields.Many2one(
        comodel_name="firebase.account",
        string="Account",
        ondelete="cascade",
        required=True
    )
    partner_id = fields.Many2one(
        string="Partner",
        comodel_name="res.partner",
        ondelete="restrict",
        required=True
    )
    uuid = fields.Char(
        string="Firebase UUID"
    )
    user = fields.Char(
        string="User"
    )
    code = fields.Char(
        string="Default Pass"
    )

    def cron_remote_sync(self, limit=60):
        Auth_obj = self.env[self._name].sudo()
        users = Auth_obj.search([
            ('uuid', '=', False)
        ], limit=limit)
        for user in users:
            app = user.account_id._get_app()
            fb_user = auth.create_user(
                app=app,
                display_name=user.partner_id.display_name,
                email=user.user,
                password=user.code
            )
            if fb_user and fb_user.uid:
                user.write({
                    'uuid': fb_user.uid
                })

    def cron_local_sync(self):
        auth_obj = self.env[self._name]
        accounts = self.env['firebase.account'].sudo().search([
            ('auth', '!=', 'off')
        ])
        for ac in accounts:
            if not ac.auth_field_pass or not ac.auth_field_user:
                continue
            partners = self.env['res.partner'].sudo().search(ac._get_auth_eval_domain())
            for p in partners:
                firebase_user = auth_obj.sudo().search([('partner_id', '=', p.id)])
                if firebase_user:
                    continue
                user_val = "{}{}".format(
                    getattr(p, ac.auth_field_user.name, ""),
                    ac.auth_field_user_sufix if ac.auth_field_user_sufix else ""
                )
                pass_val = getattr(p, ac.auth_field_pass.name, "")
                if not pass_val:
                    continue
                if len(pass_val) < 6:
                    continue
                auth_obj.sudo().create({
                    'account_id': ac.id,
                    'partner_id': p.id,
                    'user': user_val,
                    'code': pass_val,
                })
