import os

import core.app_scenario

from . import default_params


class OfficeAppsLaunchClose(core.app_scenario.Scenario):
    default_params.run()
    actions = None

    def setUp(self):
        actions_json = os.path.join(
            os.path.dirname(__file__), "office_apps_launch_close.json"
        )
        self.actions = self.load_action_json(actions_json)
        core.app_scenario.Scenario.setUp(self)

    def runTest(self):
        run_test = self._find_next_type("Run Test", json=self.actions)
        if run_test:
            self.run_actions(run_test["children"])

    def tearDown(self):
        core.app_scenario.Scenario.tearDown(self)

    def kill(self):
        return
