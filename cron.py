from .models import MachineLogModel, MachineChallenge

from CTFd.models import db
from CTFd.plugins.machine_challenges.utils import ecs_delete_secgroup

from flask_apscheduler import APScheduler, STATE_RUNNING
from datetime import datetime

import logging

logger = logging.getLogger('machine')

def load(app):
    def terminate_expired_machine():
        with app.app_context():
            machines = MachineLogModel.query.filter(
                MachineLogModel.status == 2,
            ).all()
            for machine in machines:
                try:
                    ecs_delete_secgroup(machine.detail)
                    machine.status = 0
                    db.session.commit()
                except:
                    logger.info(f"[CRON] Failed to delete security group for machine id {machine.id}")

            machines = MachineLogModel.query.filter(
                MachineLogModel.status == 1,
                MachineLogModel.time_end <= datetime.utcnow()
            ).all()    
            for machine in machines:
                logger.info(f"[CRON] Terminating machine id {machine.id}")
                MachineChallenge.terminatemachine(machine.user, machine.challenge)    

    scheduler = APScheduler()
    if scheduler.state == STATE_RUNNING:
        scheduler.shutdown()
    scheduler.init_app(app)
    scheduler.add_job(id = 'Terminate expired machine', func = terminate_expired_machine, trigger = 'cron', minute='*/5')
    scheduler.start()