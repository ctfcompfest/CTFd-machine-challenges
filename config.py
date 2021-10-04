from CTFd.utils import get_config, set_config
from os import environ

class MachineEcsConfig(object):
    AWS_ACCESS_KEY_ID : str = get_config('MACHINECHALL_ACCESS_KEY') 
    AWS_SECRET_ACCESS_KEY : str = get_config('MACHINECHALL_SECRET_KEY')
    AWS_REGION_NAME : str = get_config('MACHINECHALL_REGION') 
    AWS_ECS_CLUSTER : str = get_config('MACHINECHALL_ECS_CLUSTER') 
    AWS_VPC_ID : str = get_config('MACHINECHALL_VPC_ID') 

def load(app):
    set_config('MACHINECHALL_ACCESS_KEY', app.config.get('MACHINECHALL_ACCESS_KEY', environ.get('MACHINECHALL_ACCESS_KEY')))
    set_config('MACHINECHALL_SECRET_KEY', app.config.get('MACHINECHALL_SECRET_KEY', environ.get('MACHINECHALL_SECRET_KEY')))
    set_config('MACHINECHALL_REGION', app.config.get('MACHINECHALL_REGION', environ.get('MACHINECHALL_REGION')))
    set_config('MACHINECHALL_ECS_CLUSTER', app.config.get('MACHINECHALL_ECS_CLUSTER', environ.get('MACHINECHALL_ECS_CLUSTER')))
    set_config('MACHINECHALL_VPC_ID', app.config.get('MACHINECHALL_VPC_ID', environ.get('MACHINECHALL_VPC_ID')))