from tervis.dependencies import DependencyMount, DependencyDescriptor
from tervis.environment import CurrentEnvironment


class CurrentOperation(DependencyDescriptor):
    pass


class Operation(DependencyMount):
    env = CurrentEnvironment()

    def __init__(self, env, req=None, project_id=None):
        DependencyMount.__init__(self,
            parent=env,
            scope='operation',
            descriptor_type=CurrentOperation
        )
        self.req = req
        self.project_id = project_id
