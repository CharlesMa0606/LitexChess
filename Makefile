.PHONY: bootstrap install test formal-check verify run zip

bootstrap:
	bash scripts/bootstrap_litex.sh

install:
	python -m pip install -e '.[dev]'

formal-check:
	bash scripts/check_litex.sh

test:
	pytest
	node --check frontend/app.js
	node --check frontend/notation.js
	node --check frontend/textbook.js
	node scripts/verify_notation.js

verify:
	python scripts/verify_release.py

run:
	bash scripts/run_dev.sh

zip:
	bash scripts/package.sh
