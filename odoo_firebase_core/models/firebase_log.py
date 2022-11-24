from odoo import fields, models


class FirebaseLog(models.Model):
    _name = "firebase.log"
    _description = "Firebase LOG"

    model_name = fields.Char(
        string="Odoo Model"
    )
    path_name = fields.Char(
        string="Firebase Path"
    )
    res_id = fields.Integer(
        string="Odoo Model ID"
    )
    path_id = fields.Char(
        string="Firebase Document ID"
    )
    operation_type = fields.Selection(
        string="Operation",
        selection=[
            ('create', 'Create'),
            ('write', 'Write'),
            ('unlink', 'Unlink'),
        ]
    )
    data = fields.Text(
        string="Data"
    )
    is_processed = fields.Boolean(
        string="Processed",
        default=False
    )
    date_processed = fields.Datetime(
        string="Date processed"
    )

    def cron_clean(self):
        import datetime
        self.env[self._name].sudo().search([
            ('create_date', '<', datetime.datetime.now() - datetime.timedelta(days=7))
        ]).unlink()
