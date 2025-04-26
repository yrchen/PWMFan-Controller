# Makefile for PWM Fan Controller Localization

# Variables
APP_NAME = pwmfan_controller
SOURCE_FILE = src/pwm_fan_controller.py
POT_FILE = locales/$(APP_NAME).pot
LANGUAGES = en zh_TW # Add more language codes here if needed
PO_FILES = $(foreach lang,$(LANGUAGES),locales/$(lang)/LC_MESSAGES/$(APP_NAME).po)
MO_FILES = $(foreach lang,$(LANGUAGES),locales/$(lang)/LC_MESSAGES/$(APP_NAME).mo)

# Default target
all: mo

# Target to update the POT template file
.PHONY: pot
pot:
	@echo "Updating POT template file: $(POT_FILE)..."
	xgettext --language=Python --keyword=_ --output=$(POT_FILE) $(SOURCE_FILE)

# Target to update PO files from POT
.PHONY: update-po
update-po: pot
	@echo "Updating PO files..."
	$(foreach po,$(PO_FILES), msgmerge --update $(po) $(POT_FILE);)

# Target to compile MO files from PO files
.PHONY: mo
mo: $(MO_FILES)

locales/%/LC_MESSAGES/$(APP_NAME).mo: locales/%/LC_MESSAGES/$(APP_NAME).po
	@echo "Compiling $< to $@..."
	msgfmt $< -o $@

# Convenience target to update PO files and compile MO files
.PHONY: translate
translate: update-po mo

# Target to clean generated files
.PHONY: clean
clean:
	@echo "Cleaning generated localization files..."
	rm -f $(POT_FILE)
	rm -f $(MO_FILES) 