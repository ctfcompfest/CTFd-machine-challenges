import os

from . import api, models, logger, cron, view, config

from CTFd.plugins import register_plugin_assets_directory

def load(app):
    enabled = app.config.get('MACHINECHALL_ENABLED', os.getenv('MACHINECHALL_ENABLED', 'false').lower() == 'true')
    if not enabled: return

    register_plugin_assets_directory(
        app, base_path="/plugins/machine_challenges/assets/"
    )

    config.load(app)
    logger.load(app)
    models.load(app)
    cron.load(app)
    api.load(app)
    view.load(app)
