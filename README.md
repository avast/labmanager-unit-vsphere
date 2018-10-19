# LabManager Unit für vSphere

REST service for machine control on vmWare vSphere.

## Development

Project developers need to adhere to the following rules.

Contributors outside QA Automation team are required to discuss the contribution via GitHub Issue first. 

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
* Python code changes need to follow PEP8, with following mods:
    * indent using 4 spaces only
    * line length limit extended to 100
* New features should be covered via specs

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
    * branches named `docs_*`, snake case
    * single commit, message starting with `docs: `

* Chores
    * branches named `chore_*`, snake case
    * single commit, message starting with `chore: `

## Production use

The service is not production ready yet.
