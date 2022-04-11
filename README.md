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
* create new database, sequence, table
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
                id bigint DEFAULT nextval('public.documents_id_seq'::regclass) NOT NULL primary key,
                type character varying(128),
                data json
            );
            ALTER TABLE public.documents OWNER TO postgres;
  ```
* create new indexes
  ```
  CREATE INDEX idx10 ON public.documents USING btree (((data ->> 'type'::text)));
  CREATE INDEX idx11 ON public.documents USING btree (((data ->> 'lock'::text)));
  CREATE INDEX idx3 ON public.documents USING btree (type, ((data ->> 'state'::text)));
  CREATE INDEX idx4 ON public.documents USING btree (type, id);
  ```
* copy file `config/lm-unit.yaml.example` to `config/lm-unit.yaml`
* adjust the contents of `config/lm-unit.yaml`
    * the config already contains some hints
    * please fill in database data `db:` section    
    * please fill in vSphere data in `vsphere:` section

* install Python 3.6
* install pipenv
  ```
  pip install pipenv
  ```
* install project dependencies:
  ```
  PIPENV_VENV_IN_PROJECT=1 pipenv install
  ```


### Production usage
* Please repeat the database creation for production use
* create production section of your config
* the sevice consists of four microservices that are specified in `Procfile`, so please run all microservices by using e.g. systemd services, docker containers or k8s.

### Code
* Python code changes need to follow PEP8, with following mods:
    * indent using 4 spaces only
    * line length limit extended to 120
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


