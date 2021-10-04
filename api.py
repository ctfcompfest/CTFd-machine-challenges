from .models import MachineLogModel, MachineChallenge
from .schema import MachineLogSchema

from flask import request, views
from flask_restx import Resource, Namespace
from werkzeug.exceptions import NotFound, abort

from CTFd.api import CTFd_API_v1
from CTFd.api.v1.challenges import Challenge as ChallengeAPI
from CTFd.models import Challenges, Solves
from CTFd.plugins.challenges import get_chal_class
from CTFd.utils import config
from CTFd.utils.dates import ctf_paused
from CTFd.utils.decorators import admins_only, during_ctf_time_only, require_verified_emails
from CTFd.utils.decorators.visibility import check_challenge_visibility
from CTFd.utils.user import authed, get_current_user, is_admin

import logging

machineLogDumper = MachineLogSchema()
logger = logging.getLogger('machine')

class ChallengeAPIMod(ChallengeAPI, views.View):
    @check_challenge_visibility
    @during_ctf_time_only
    @require_verified_emails
    def get(self, challenge_id):
        resp = super().get(challenge_id)
        if is_admin():
            return resp
        else:
            if isinstance(resp, dict):
                resp['data'].pop('machine', None)
                return resp
            else: return resp

    @admins_only
    def patch(self, challenge_id):
        return super().patch(challenge_id)

    @admins_only
    def delete(self, challenge_id):
        return super().delete(challenge_id)


machine_namespace = Namespace("machines")
@machine_namespace.route("")
class MachineList(Resource):
    @check_challenge_visibility
    @during_ctf_time_only
    @require_verified_emails
    @machine_namespace.doc(
        description="Endpoint to start a machine for a specific Challenge"
    )
    def post(self):
        if authed() is False:
            return {"success": True, "data": {"status": "authentication_required"}}, 403
        
        data = request.get_json() or request.form
        challenge_id = data.get("challenge_id")
        challenge = Challenges.query.filter_by(id = challenge_id).first_or_404()
        user = get_current_user()

        if is_admin() == False:
            if ctf_paused():
                return {
                        "success": True,
                        "data": {
                            "status": "paused",
                            "message": "{} is paused".format(config.ctf_name()),
                        },
                    }, 403

            if challenge == None or challenge.state == "hidden":
                abort(404)
            if challenge.state == "locked":
                abort(403)
            if challenge.requirements:
                requirements = challenge.requirements.get("prerequisites", [])
                solve_ids = (
                    Solves.query.with_entities(Solves.challenge_id)
                    .filter_by(account_id=user.account_id)
                    .order_by(Solves.challenge_id.asc())
                    .all()
                )
                solve_ids = {solve_id for solve_id, in solve_ids}
                prereqs = set(requirements)
                if solve_ids < prereqs:
                    abort(403)


        chall_class = get_chal_class(challenge.type)
        if not hasattr(chall_class, "startmachine"):
            abort(400)

        try:
            machine = chall_class.startmachine(user, challenge)
            response = machineLogDumper.dump(machine)
        except Exception as e:
            logger.error(f"Failed start machine: {user.name} - {challenge_id} - {str(e)}")
            return {"success": False, "errors": str(e)}, 500
        return {"success": True, "data": response.data}


    @admins_only
    @machine_namespace.doc(
        description="Endpoint to terminate multi machine"
    )
    def delete(self):
        data = request.get_json() or request.form
        machine_ids = data.get("machine_ids")
        if machine_ids == None or not isinstance(machine_ids, list):
            abort(400)
        
        machines = MachineLogModel.query.filter(
            MachineLogModel.status == 1,
            MachineLogModel.id.in_(machine_ids)
        ).all()

        err = []
        for machine in machines:
            try:
                MachineChallenge.terminatemachine(machine.user, machine.challenge)
            except Exception as e:
                logger.error(f"Failed bulk terminate machine: {machine.id} - {str(e)}")
                err.append(f"ERROR: {machine.id} - {str(e)}")
        if len(err) == 0:
            return {"success": True}
        else:
            return {"success": False, "errors": err}, 500


@machine_namespace.route("/<challenge_id>")
class Machine(Resource):
    @check_challenge_visibility
    @during_ctf_time_only
    @require_verified_emails
    @machine_namespace.doc(
        description="Endpoint to update the status of a machine for a specific challenge"
    )
    def get(self, challenge_id):
        if authed() is False:
            return {"success": True, "data": {"status": "authentication_required"}}, 403
        
        user = get_current_user()
        challenge = Challenges.query.filter_by(id=challenge_id).first_or_404()

        chall_class = get_chal_class(challenge.type)
        if not hasattr(chall_class, "updatemachine"):
            abort(400)

        try:
            machine = chall_class.updatemachine(user, challenge)
            response = machineLogDumper.dump(machine)
        except NotFound as e:
            return {'success': False, 'errors': str(e)}
        except Exception as e:
            logger.error(f"Failed update machine: {user.name} - {challenge_id} - {str(e)}")
            return {"success": False, "errors": str(e)}, 500
        return {"success": True, "data": response.data}


    @check_challenge_visibility
    @during_ctf_time_only
    @require_verified_emails
    @machine_namespace.doc(
        description="Endpoint to terminate a machine for a specific challenge"
    )
    def delete(self, challenge_id):
        if authed() is False:
            return {"success": True, "data": {"status": "authentication_required"}}, 403
        
        user = get_current_user()
        challenge = Challenges.query.filter_by(id=challenge_id).first_or_404()

        chall_class = get_chal_class(challenge.type)
        if not hasattr(chall_class, "terminatemachine"):
            abort(400)

        try:
            stt = chall_class.terminatemachine(user, challenge)
        except Exception as e:
            logger.error(f"Failed terminate machine: {user.name} - {challenge_id} - {str(e)}")
            return {"success": False, "errors": str(e)}, 500
        return {"success": stt}


@machine_namespace.route("/ping")
class MachinePing(Resource):
    def get(self):
        return {"success": True, "data": "pong"}


def load(app):
    app.view_functions['api.challenges_challenge'] = ChallengeAPIMod.as_view('challenges_challenge_mod')
    CTFd_API_v1.add_namespace(machine_namespace, "/machines")
    