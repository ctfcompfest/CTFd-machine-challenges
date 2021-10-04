from flask import Blueprint
from werkzeug.exceptions import NotFound

from . import utils

from CTFd.cache import cache
from CTFd.models import db
from CTFd.plugins.challenges import CHALLENGE_CLASSES
from CTFd.plugins.dynamic_challenges import DynamicChallenge, DynamicValueChallenge
from CTFd.plugins.migrations import upgrade

from os import urandom
from datetime import datetime, timedelta

import json

def getrandomslug():
    return f"ctfd-{urandom(16).hex()}"

class MachineLogModel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chall_id = db.Column(db.Integer, db.ForeignKey("challenges.id", ondelete="CASCADE"))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"))
    task_id = db.Column(db.String(255))
    # Status
    # 0 = stopped
    # 1 = running
    # 2 = stopped but security group not deleted
    status = db.Column(db.Integer)
    time_str = db.Column(db.DateTime)
    time_end = db.Column(db.DateTime)
    detail = db.Column(db.Text)
    
    user = db.relationship("Users", foreign_keys="MachineLogModel.user_id", lazy="select")
    challenge = db.relationship("Challenges", foreign_keys="MachineLogModel.chall_id", lazy="select")

class MachineChallModel(DynamicChallenge):
    __mapper_args__ = {"polymorphic_identity": "machine"}
    id = db.Column(
        db.Integer, db.ForeignKey("dynamic_challenge.id", ondelete="CASCADE"), primary_key=True
    )
    slug = db.Column(db.Text(25), unique=True, default=getrandomslug) 
    duration = db.Column(db.Integer, default=60)
    config = db.Column(db.Text, default="")

    def __init__(self, *args, **kwargs):
        super(MachineChallModel, self).__init__(**kwargs)

class MachineChallenge(DynamicValueChallenge):
    id = "machine"  # Unique identifier used to register challenges
    name = "machine"  # Name of a challenge type
    templates = {  # Handlebars templates used for each aspect of challenge editing & viewing
        "create": "/plugins/machine_challenges/assets/create.html",
        "update": "/plugins/machine_challenges/assets/update.html",
        "view": "/plugins/machine_challenges/assets/view.html",
    }
    scripts = {  # Scripts that are loaded when a template is loaded
        "create": "/plugins/machine_challenges/assets/create.js",
        "update": "/plugins/machine_challenges/assets/update.js",
        "view": "/plugins/machine_challenges/assets/view.js",
    }
    # Route at which files are accessible. This must be registered using register_plugin_assets_directory()
    route = "/plugins/machine_challenges/assets/"
    # Blueprint used to access the static_folder directory.
    blueprint = Blueprint(
        "machine_challenges",
        __name__,
        template_folder="templates",
        static_folder="assets",
    )
    challenge_model = MachineChallModel

    @classmethod
    def create(cls, request):
        """
        This method is used to process the challenge creation request.

        :param request:
        :return:
        """
        data = request.form or request.get_json()
        data['slug'] = getrandomslug()
        data['config'] = utils.ecs_register_task(data['slug'], data.get('config'))
        
        challenge = cls.challenge_model(**data)
        db.session.add(challenge)
        db.session.commit()

        return challenge


    @classmethod
    def update(cls, challenge, request):
        """
        This method is used to update the information associated with a challenge. This should be kept strictly to the
        Challenges table and any child tables.

        :param challenge:
        :param request:
        :return:
        """
        data = request.form or request.get_json()
        if data.get('config') != None and challenge.config != data.get('config'):
            data['config'] = utils.ecs_register_task(challenge.slug, data.get('config'))
        for attr, value in data.items():
            setattr(challenge, attr, value)

        db.session.commit()
        return challenge


    @classmethod
    def read(cls, challenge):
        """
        This method is in used to access the data of a challenge in a format processable by the front end.

        :param challenge:
        :return: Challenge object, data dictionary to be returned to the user
        """
        challenge = MachineChallModel.query.filter_by(id=challenge.id).first()
        data = {
            "id": challenge.id,
            "name": challenge.name,
            "value": challenge.value,
            "initial": challenge.initial,
            "decay": challenge.decay,
            "minimum": challenge.minimum,
            "description": challenge.description,
            "category": challenge.category,
            "state": challenge.state,
            "max_attempts": challenge.max_attempts,
            "type": challenge.type,
            "type_data": {
                "id": cls.id,
                "name": cls.name,
                "templates": cls.templates,
                "scripts": cls.scripts,
            },
        }
        return data
    

    @classmethod
    def delete(cls, challenge):
        """
        This method is used to delete the resources used by a challenge.

        :param challenge:
        :return:
        """
        utils.ecs_delete_task(challenge.slug)
        super().delete(challenge)


    @classmethod
    def startmachine(cls, user, challenge):
        """
        This method is used to start a machine for a user and a challenge

        :param user:
        :param challenge:
        :return: MachineLogModel object, data dictionary to be returned to the user
        """
        CONTAINER_NUMLIMIT = 1
        active_machine = MachineLogModel.query.filter(
            MachineLogModel.status == 1,
            MachineLogModel.user_id == user.id,
            MachineLogModel.time_end > datetime.utcnow()
        ).all()

        if len(active_machine) >= CONTAINER_NUMLIMIT:
            raise Exception('You have reached the maximum machine limit. Terminate another machine first.')

        stt_machine = utils.ecs_start_machine(challenge.slug, challenge.config)
        machine_log = MachineLogModel(
            chall_id = challenge.id,
            user_id = user.id,
            task_id = stt_machine['taskArn'],
            status = 1,
            time_str = datetime.utcnow(),
            time_end = datetime.utcnow() + timedelta(minutes=challenge.duration),
            detail = json.dumps(stt_machine)
        )

        db.session.add(machine_log)
        db.session.commit()

        return machine_log


    @classmethod
    def updatemachine(cls, user, challenge):
        """
        This method is used to update machine status for a user and a challenge.

        :param user:
        :param challenge:
        :return: MachineLogModel object, data dictionary to be returned to the user
        """
        active_machine = MachineLogModel.query.filter(
            MachineLogModel.status == 1,
            MachineLogModel.user_id == user.id,
            MachineLogModel.chall_id == challenge.id
        ).first()
        if active_machine == None:
            raise NotFound('Machine log not found.')

        cache_key = f'machine:{active_machine.id}'
        if cache.get(cache_key) == None:
            new_detail = utils.ecs_update_machine(active_machine.detail)
            active_machine.detail = json.dumps(new_detail)
            if new_detail['lastStatus'] == 'RUNNING':
                cache.set(cache_key, active_machine.detail, 5 * 60)

        db.session.commit()
        return active_machine


    @classmethod
    def terminatemachine(cls, user = None, challenge = None):
        """
        This method is used to terminate machine for a user and a challenge
        User and Challenge object is optional filtering.

        :param user:
        :param challenge:
        :return: Boolean, indicate job is successfully executed or not
        """
        active_machines = MachineLogModel.query.filter(MachineLogModel.status == 1)
        if user != None:
            active_machines = active_machines.filter(MachineLogModel.user_id == user.id)
        if challenge != None:
            active_machines = active_machines.filter(MachineLogModel.chall_id == challenge.id)
        active_machines = active_machines.all()

        for active_machine in active_machines:
            stt_machine = utils.ecs_terminate_machine(active_machine.task_id)
            if not stt_machine:
                return False

            active_machine.status = 2
            active_machine.time_end = datetime.utcnow()
            db.session.commit()

        return True


    @classmethod
    def statusmachine(cls, user = None, challenge = None):
        """
        This method is used to get machine status for a user and a challenge.
        User and Challenge object is optional filtering.

        :param user:
        :param challenge:
        :return: List of MachineLogModel object, list of data dictionary to be returned to the user
        """
        active_machines = MachineLogModel.query.filter(MachineLogModel.status == 1)
        if user != None:
            active_machines = active_machines.filter(MachineLogModel.user_id == user.id)
        if challenge != None:
            active_machines = active_machines.filter(MachineLogModel.chall_id == challenge.id)
        active_machines = active_machines.all()

        return active_machines

def load(app):
    upgrade()

    CHALLENGE_CLASSES["machine"] = MachineChallenge
