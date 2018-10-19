# LabManager Unit für vSphere

REST service for machine control on vmWare vSphere.

## Development

Project developers are required to adhere to the following rules.

Contributors outside QA Automation team are required to discuss the contribution first via GitHub Issue.

### Technical requirements for development
* Install Python 3.6
* Install pipenv
  ```
  PIPENV_VENV_IN_PROJECT=1 pip install pipenv
  ```
* Install project dependencies:
  ```
  pipenv install
  ```

### Code
* Python code changes need to follow PEP8, with following tweaks:
    * indentation restricted to 4 spaces only
    * allowing 100 character lines instead of 80
* New features covered via specs

### Branching
* Features
    * branches named `feat_*`, snake case
    * single commit, message starting with `feat: `

* Fixes
    * branches named `fix_*`, snake case
    * single commit, message starting with `fix: `

* Refactoring
    * branches named `refactor_*`, snake case
    * single commit, message starting with `refactor: `

* Documentation
    * branches named `doc_*`, snake case
    * single commit, message starting with `doc: `

* Chores
    * branches named `chore_*`, snake case
    * single commit, message starting with `chore: `

## Production use

The service is not production ready yet.
