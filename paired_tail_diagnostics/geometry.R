args <- commandArgs(TRUE)
root <- args[1]
libs <- strsplit(Sys.getenv('PAPER1_CALIBRATION_LIBRARIES'), .Platform$path.sep, fixed=TRUE)[[1]]
.libPaths(c(libs[nzchar(libs)], .libPaths()))
source(file.path(root, 'analysis/common.R'), encoding='UTF-8')
source(file.path(root, 'paired_count_calibration/engine.R'))
p <- jsonlite::read_json(args[2], simplifyVector=FALSE)
rows <- lapply(p$scenarios, function(s) {
  d <- make_design(s)
  a0 <- solve(crossprod(d$x0), t(d$x0))
  a1 <- solve(crossprod(d$x1), t(d$x1))
  contrast <- a1[2,] - a0[2,]
  H <- d$x1 %*% a1
  M <- diag(s$n) - H
  weights <- contrast^2 / (1 - diag(H))^2
  B <- M %*% diag(weights) %*% M
  tr <- sum(diag(B))
  data.frame(scenario=s$id, n=s$n, rho=s$rho, reference_df=s$n-ncol(d$x1),
    mean_HC3_variance_over_true=tr/sum(contrast^2),
    moment_equivalent_df=tr^2/sum(B*B),
    numerator_residual_orthogonality=max(abs(M %*% contrast)),
    max_leverage=max(diag(H)))
})
write.csv(do.call(rbind, rows), args[3], row.names=FALSE)
