libs <- commandArgs(trailingOnly=TRUE)
if (length(libs)) .libPaths(unique(c(libs, .libPaths())))
suppressPackageStartupMessages(library(limma))
m <- read.csv(file("stdin"), check.names=FALSE)
x0 <- as.matrix(m[c("intercept", "target", "nuisance")])
z <- as.matrix(m[c("z1", "z2")])
w <- m$weight
y <- t(as.matrix(m[startsWith(names(m), "gene")]))

# Extended minus baseline: contrast weights on the added coefficients are -a.
a <- qr.solve(x0 * sqrt(w), z * sqrt(w))["target", ]
cvec <- matrix(c(rep(0, ncol(x0)), -a), ncol=1)
design <- contrastAsCoef(cbind(x0, z), cvec)
fit <- lmFit(y, design$design, weights=matrix(w, nrow(y), length(w), byrow=TRUE))
delta <- fit$coefficients[, design$coef]
se <- fit$stdev.unscaled[, design$coef] * fit$sigma
cat(sprintf("VERSIONS\t%s\t%s\n", as.character(getRversion()), as.character(packageVersion("limma"))))
cat("gene,delta,se\n")
cat(sprintf("%s,%.17g,%.17g\n", rownames(y), delta, se), sep="")
