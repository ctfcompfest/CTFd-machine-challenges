from os import urandom
from .config import MachineEcsConfig

import boto3
import json

awssession = boto3.Session(
    aws_access_key_id=MachineEcsConfig.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=MachineEcsConfig.AWS_SECRET_ACCESS_KEY,
    region_name=MachineEcsConfig.AWS_REGION_NAME
)

def ecs_register_task(slug, cfg_str):
    if cfg_str == "" or cfg_str == None: return None
    client = awssession.client('ecs')

    cfg = json.loads(cfg_str)
    task_def = cfg['taskDefinition']
    task_def['family'] = slug
    
    client.register_task_definition(**task_def)
    return json.dumps(cfg, indent=2)


def ecs_delete_task(slug):
    client = awssession.client('ecs')

    def delete_task_revision():
        r = client.list_task_definitions(familyPrefix=slug)
        task_list = r['taskDefinitionArns']
        for arn in task_list:
            client.deregister_task_definition(taskDefinition=arn)
        return r.get('nextToken')
        
    nextToken = delete_task_revision()
    while nextToken:
        nextToken = delete_task_revision()

    ecs_terminate_multimachine(slug)


def ecs_delete_multitask(prefix):    
    client = awssession.client('ecs')

    nextToken = "init"
    while nextToken:
        if nextToken == "init": nextToken = ""
        r = client.list_task_definition_families(familyPrefix=prefix, status="ACTIVE", nextToken=nextToken)
        for family in r['families']:
            ecs_delete_task(family)
        nextToken = r.get('nextToken')


def fargate_get_networks(runtask, resp):
    for attachment in runtask.get("attachments", []):
        for detail in attachment.get("details", []):
            if detail.get("name") == "networkInterfaceId":
                eni_id = detail.get("value")
                eni = awssession.resource('ec2').NetworkInterface(eni_id)
                
                resp['networkInterfaceId'] = eni_id
                resp['publicIp'] = eni.association_attribute['PublicIp']
                resp['subnetId'] = eni.subnet_id
                for secgroup in eni.groups:
                    resp['securityGroupId'].append(secgroup['GroupId'])


def fargate_get_containers(taskDef):
    containers = []
    for container in taskDef['containerDefinitions']:
        accum = {
            'name': container['name'],
            'portMappings': []
        }
        for port in container['portMappings']:
            port['hostPort'] = port['containerPort']
            accum['portMappings'].append(port)
        if len(accum['portMappings']) > 0:
            containers.append(accum)
    return containers


def external_get_networks(runtask, resp):
    ecs = awssession.client('ecs')
    ssm = awssession.client('ssm')

    containers = ecs.describe_container_instances(
        cluster=MachineEcsConfig.AWS_ECS_CLUSTER,
        containerInstances=[
            runtask['containerInstanceArn'],
        ]
    )
    container = containers['containerInstances'][0]

    instances = ssm.describe_instance_information(
        InstanceInformationFilterList=[
            {
                'key': 'InstanceIds',
                'valueSet': [
                    container['ec2InstanceId'],
                ]
            },
        ],
    )
    instance = instances['InstanceInformationList'][0]
    resp['publicIp'] = instance['IPAddress']


def external_get_containers(cfg):
    containers = []
    for container in cfg['containers']:
        accum = {
            'name': container['name'],
            'portMappings': []
        }
        hostport_set = set()
        for port in container['networkBindings']:
            if port['hostPort'] in hostport_set:
                continue
            hostport_set.add(port['hostPort'])
            accum['portMappings'].append(port)

        if len(accum['portMappings']) > 0:
            containers.append(accum)
    return containers


def parse_runtask_response(runtask, cfg = None, old = None):
    resp = {
        "launchType": runtask['launchType'],
        "taskArn": runtask['taskArn'],
        "taskDefinitionArn": runtask['taskDefinitionArn'],
        "containers": [],
        "publicIp": "",
        "networkInterfaceId": "",
        "subnetId": "",
        "securityGroupId": []
    }
    if old != None: resp = old

    resp['lastStatus'] = runtask['lastStatus']
    resp['desiredStatus'] = runtask['desiredStatus']
    
    if cfg != None:
        if runtask['launchType'] == 'FARGATE':
            resp['containers'] = fargate_get_containers(cfg['taskDefinition'])
    if runtask['lastStatus'] == 'RUNNING':
        if runtask['launchType'] == 'FARGATE':
            resp['securityGroupId'] = list()
            fargate_get_networks(runtask, resp)
        else:
            resp['containers'] = list()
            resp['containers'] = external_get_containers(runtask)
            external_get_networks(runtask, resp)
    return resp


def generate_network_conf(slug, networks_opt):
    ec2 = boto3.resource(
        'ec2',
        aws_access_key_id=MachineEcsConfig.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=MachineEcsConfig.AWS_SECRET_ACCESS_KEY,
        region_name=MachineEcsConfig.AWS_REGION_NAME
    )
    vpc = ec2.Vpc(MachineEcsConfig.AWS_VPC_ID)
    subnets_it = vpc.subnets.all()
    subnets = [elm for elm in subnets_it]
    if len(subnets) == 0:
        subnet = vpc.create_subnet(CidrBlock='172.0.0.0/16')
    else:
        subnet = subnets[0]

    secgroup = vpc.create_security_group(GroupName=f'ctf-sg-{urandom(8).hex()}', Description = slug)
    for rule in networks_opt.get('inbound', []):
        secgroup.authorize_ingress(**rule)
    for rule in networks_opt.get('outbound', []):
        secgroup.authorize_egress(**rule)
    return {
        'awsvpcConfiguration': {
            'subnets': [subnet.id],
            'securityGroups': [secgroup.id],
            'assignPublicIp': 'ENABLED'
        }
    }


def ecs_start_machine(slug, cfg_str):
    client = awssession.client('ecs')
    
    cfg = json.loads(cfg_str)
    launchType = cfg.get('launchType', 'FARGATE')
    networks = cfg.get('networks', {'inbound': [], 'outbound': []})

    runtask_options = {
        'cluster': MachineEcsConfig.AWS_ECS_CLUSTER,
        'count': 1,
        'launchType': launchType,
        'taskDefinition': slug
    }

    if launchType == "FARGATE":
        runtask_options['networkConfiguration'] = generate_network_conf(slug, networks)
    
    runtask_resp = client.run_task(**runtask_options)['tasks'][0]
    return parse_runtask_response(runtask_resp, cfg)


def ecs_update_machine(oldStt_str):
    client = awssession.client('ecs')
    oldStt = json.loads(oldStt_str)
    taskArn = oldStt['taskArn']

    resp = client.describe_tasks(cluster=MachineEcsConfig.AWS_ECS_CLUSTER, tasks=[taskArn])
    runtask_resp = resp['tasks'][0]

    return parse_runtask_response(runtask_resp, old = oldStt)


def ecs_terminate_machine(taskArn):
    ecs = awssession.client('ecs')
    ecs.stop_task(
        cluster=MachineEcsConfig.AWS_ECS_CLUSTER,
        task=taskArn
    )
    
    return True


def ecs_terminate_multimachine(family):
    client = awssession.client('ecs')
    r = client.list_tasks(cluster=MachineEcsConfig.AWS_ECS_CLUSTER, family=family)
    taskArns = r['taskArns']
    for task in taskArns:
        ecs_terminate_machine(task)


def ecs_delete_secgroup(cfg_str):
    ec2 = awssession.client('ec2')
    cfg = json.loads(cfg_str)

    if cfg['launchType'] == 'FARGATE':
        for secgroup in cfg.get('securityGroupId', []):
            ec2.delete_security_group(GroupId=secgroup)