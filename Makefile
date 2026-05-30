.PHONY: run test py-test js-test

run:
	PYTHONPATH=src python3 -m taskpulse.server

test: py-test js-test

py-test:
	PYTHONPATH=src python3 -m unittest discover -s tests

js-test:
	npm test
