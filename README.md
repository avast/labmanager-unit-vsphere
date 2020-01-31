# LabManager Unit für vSphere

REST service for machine control on vmWare vSphere.

## Development

Project developers need to adhere to the following rules.

Contributors outside QA Automation team are required to discuss the contribution via GitHub Issue first. 

### Technical requirements for development
* install PostgreSQL 10.6 or newer
* enter the PostgreSQL prompt:
  ```
  psql -U postgres
  ```
* create new table
  ```
  create database "lm-unit-ok_dev";
            \c "lm-unit-ok_dev";
            CREATE SEQUENCE public.documents_id_seq
                START WITH 1
                INCREMENT BY 1
                NO MINVALUE
                NO MAXVALUE
                CACHE 1;
            ALTER TABLE public.documents_id_seq OWNER TO postgres;
            CREATE TABLE public.documents (
                id bigint DEFAULT nextval('public.documents_id_seq'::regclass) NOT NULL,
                type character varying(128),
                data json
            );
            ALTER TABLE public.documents OWNER TO postgres;
  ```
* copy file `config/lm-unit.yaml.example` to `config/lm-unit.yaml`


* install Python 3.6
* install pipenv
  ```
  pip install pipenv
  ```
* install project dependencies:
  ```
  PIPENV_VENV_IN_PROJECT=1 pipenv install
  ```

### Code
* Python code changes need to follow PEP8, with following mods:
    * indent using 4 spaces only
    * line length limit extended to 100
* new features should be covered via specs

### Branching
* features
    * branches named `feat_*`, snake case
    * single commit, message starting with `feat: `

* fixes
    * branches named `fix_*`, snake case
    * single commit, message starting with `fix: `

* refactoring
    * branches named `refactor_*`, snake case
    * single commit, message starting with `refactor: `

* documentation
    * branches named `docs_*`, snake case
    * single commit, message starting with `docs: `

* chores
    * branches named `chore_*`, snake case
    * single commit, message starting with `chore: `

## Production use

The service is not production ready yet.
