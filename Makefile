.PHONY: docker sh exec kill all gen clean realclean test build web

UV := uv --cache-dir .uv-cache

web:
	$(UV) run --env-file .env python todo_web.py

show_db.py::
	$(UV) run --env-file .env $@

create_todo_list.py::
	$(UV) run --env-file .env $@

todo_web.py::
	$(UV) run --env-file .env $@

clean:
	rm -fr *.log
	find . -name    \*~  | xargs rm -fr
	find . -name   .\*~  | xargs rm -fr
	find . -name  \#\*\# | xargs rm -fr
	find . -name .\#\*   | xargs rm -fr

realclean: clean
	rm -fr .uv-cache
	rm -fr .docker-build-mtd.stamp
	rm -fr mtd-pgdata uv.lock models.py
	find . -name __pycache__ | xargs rm -fr
	find . -name .v\*        | xargs rm -fr
	tree -I .git -I .kelvin -I old.src -I mtd -asF
