from CTFd.models import Challenges, Users
from .models import MachineChallModel, MachineChallenge, MachineLogModel
from .utils import ecs_delete_multitask

from flask import request, Blueprint, render_template, url_for

from CTFd.admin import reset as admin_reset
from CTFd.utils.decorators import admins_only
from CTFd.utils.helpers.models import build_model_filters

@admins_only
def admin_reset_mod():
    if request.method == "POST":
        data = request.form
        if data.get("challenges"):
            MachineChallenge.terminatemachine()
            ecs_delete_multitask("ctfd")
            MachineChallModel.query.delete()
    return admin_reset() 


def load(app):
    app.view_functions['admin.reset'] = admin_reset_mod
    admin_machine = Blueprint('admin_machine', __name__, template_folder='templates')

    @admin_machine.route('/admin/machines', methods=['GET'])
    @admins_only
    def machines_list():
        q = request.args.get("q")
        field = request.args.get("field")
        page = abs(request.args.get("page", 1, type=int))
        
        filters = build_model_filters(
            model=MachineLogModel,
            query=q,
            field=field,
            extra_columns={
                "challenge_name": Challenges.name,
                "user_name": Users.name,
            },
        )

        machine_logs = (
            MachineLogModel.query.filter(*filters)
            .join(Challenges)
            .join(Users)
            .order_by(MachineLogModel.id.desc())
            .paginate(page=page, per_page=50)
        )
        args = dict(request.args)
        args.pop("page", 1)

        return render_template(
            'machines.html',
            machines=machine_logs,
            prev_page=url_for(request.endpoint, page=machine_logs.prev_num, **args),
            next_page=url_for(request.endpoint, page=machine_logs.next_num, **args),
            q=q,
            field=field,
        )

    app.register_blueprint(admin_machine)