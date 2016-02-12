#
# Build javascript assets
#
#
BROWSERIFY = node node_modules/browserify/bin/cmd.js
#
#  The files we generate at build-time
# 
DERIVED = busy.min.js

##
## Default recipe:  Rebuild whatever needs rebuilding.
## Note this is the default rule --- 'make' alone is same as 'make all'
##
all:	$(DERIVED)

##
## Make a clean start --- rebuild the whole 'dist' directory
##
clean:	
	rm -f $(DERIVED)

##
## Recipes for components 
## 

## Combine and minify javascript files with browserify
%.min.js:	%.js
	$(BROWSERIFY) $< > $@

## Special case for top-level javascript file
busy.min.js:  busy.js
	$(BROWSERIFY) $< --standalone busy > $@
