from .models import MachineLogModel
from CTFd.models import ma

class MachineLogSchema(ma.ModelSchema):
    class Meta:
        model = MachineLogModel
        fields = ('id','chall_id','status','time_str','time_end', 'detail')