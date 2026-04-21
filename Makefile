.PHONY: setup test rescore viewer clean

setup:
	pip3 install -r eval_requirements.txt
	@test -f .env || cp .env.example .env && echo "Created .env from .env.example — fill in ANTHROPIC_API_KEY"

test:
	python3 -m eval.cli run

test-single:
	python3 -m eval.cli run --case $(CASE)

test-repeats:
	python3 -m eval.cli run --repeats $(N)

rescore:
	python3 -m eval.cli rescore --traces fixture_traces/

viewer:
	python3 -m eval.cli viewer --report $(REPORT)

clean:
	rm -rf eval_traces/ eval_reports/ eval_viewer/
