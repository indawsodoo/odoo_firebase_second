from odoo import http


class WebHookController(http.Controller):

    @http.route('/odoo-firebase-core/execute', methods=['GET'], auth='public', type='http')
    def odoo_firebase_core_execute(self):
        http.request.env['firebase.account'].sudo().cron_import_data()
        return "ok"
