#!/usr/bin/env Rscript
# r_helpers/run_mainger.R
# -----------------------
# JSON-in / JSON-out bridge between the Python agent and the mainger package.
#
# Patched to match the actual mainger v0.2.0 API:
#   eta_bound_partial(beta_int, beta_ext, Sigma_int, sigma2_int, fallback=5)
#   eta_bound_full(Sigma_int, Sigma_ext, delta, sigma2_int, sigma2_ext, n_int, n_ext)
#   estimate_direction_biases(delta, Sigma_int, Sigma_ext, sigma2_ext=NULL, n_ext=NULL)
#   check_concordance(k_vals, b_vals, sigma2_int, n_int, eta)
#   spectral_advantage(k_vals, b_vals, sigma2_int, n_int, eta_grid)
#   diagnose(fit)   -- prints; we read fit$diagnostics instead

suppressPackageStartupMessages({
  # FILL IN: if mainger lives in a non-default library, uncomment and set:
  # .libPaths(c("F:/R-4.5.1/library", .libPaths()))
  library(mainger)
  library(jsonlite)
})

`%||%` <- function(a, b) if (is.null(a)) b else a

# --- Read request ---------------------------------------------------------- #
input <- paste(readLines("stdin", warn = FALSE), collapse = "\n")
req   <- fromJSON(input, simplifyVector = FALSE)
tool  <- req$tool
args  <- req$args
session <- if (file.exists(req$session_path)) readRDS(req$session_path) else list()

# --- Helper: derive internal summaries from individual data if needed ----- #
ensure_internal_summaries <- function(s) {
  if (!is.null(s$X_int) && !is.null(s$Y_int)) {
    X <- as.matrix(s$X_int); Y <- as.numeric(s$Y_int)
    n <- nrow(X); p <- ncol(X)
    if (is.null(s$beta_int) || is.null(s$Sigma_int) || is.null(s$sigma2_int)) {
      XtX <- crossprod(X)
      XtY <- crossprod(X, Y)
      bhat <- as.numeric(solve(XtX, XtY))
      resid <- Y - X %*% bhat
      if (is.null(s$beta_int))   s$beta_int   <- bhat
      if (is.null(s$Sigma_int))  s$Sigma_int  <- XtX / n
      if (is.null(s$sigma2_int)) s$sigma2_int <- as.numeric(sum(resid^2) / max(1, n - p))
    }
    if (is.null(s$n_int)) s$n_int <- n
  }
  s
}

# --- Tool implementations -------------------------------------------------- #
detect_regime <- function(args, s) {
  has_int_ind   <- isTRUE(args$has_internal_individual_data)
  has_int_marg  <- isTRUE(args$has_internal_marginal_only)
  has_ext_theta <- isTRUE(args$has_external_theta)
  has_ext_sigma <- isTRUE(args$has_external_sigma2)
  has_ref       <- isTRUE(args$has_reference_panel)

  regime <- if (!has_ext_theta) "none"
            else if (has_int_ind && has_ext_sigma) "full"
            else if (has_int_ind) "partial"
            else if (has_int_marg && has_ref) "restricted"
            else "indeterminate"

  list(regime = regime,
       reason = sprintf("internal_indiv=%s, internal_marginal=%s, ext_theta=%s, ext_sigma2=%s, ref=%s",
                        has_int_ind, has_int_marg, has_ext_theta, has_ext_sigma, has_ref))
}

compute_eta_bound <- function(args, s) {
  s <- ensure_internal_summaries(s)
  regime <- args$regime

  eta_star <- if (regime == "partial") {
    mainger::eta_bound_partial(
      beta_int = as.numeric(s$beta_int),
      beta_ext = as.numeric(s$beta_ext),
      Sigma_int = as.matrix(s$Sigma_int),
      sigma2_int = as.numeric(s$sigma2_int)
    )
  } else if (regime == "full") {
    delta <- as.numeric(s$beta_int) - as.numeric(s$beta_ext)
    mainger::eta_bound_full(
      Sigma_int = as.matrix(s$Sigma_int),
      Sigma_ext = as.matrix(s$Sigma_ext),
      delta = delta,
      sigma2_int = as.numeric(s$sigma2_int),
      sigma2_ext = as.numeric(s$sigma2_ext),
      n_int = as.integer(s$n_int),
      n_ext = as.integer(s$n_ext)
    )
  } else if (regime == "restricted") {
    # Restricted regime uses the partial bound with the reference Sigma.
    p_dim <- length(as.numeric(s$beta_ext))
    mainger::eta_bound_partial(
      beta_int = as.numeric(s$beta_int %||% rep(0, p_dim)),
      beta_ext = as.numeric(s$beta_ext),
      Sigma_int = as.matrix(s$Sigma_ref),
      sigma2_int = as.numeric(s$sigma2_int)
    )
  } else {
    stop(sprintf("Unknown regime '%s'", regime))
  }

  list(eta_star = unname(eta_star), regime = regime)
}

check_concordance <- function(args, s) {
  s <- ensure_internal_summaries(s)
  if (is.null(s$Sigma_ext)) {
    stop("check_concordance requires Sigma_ext, which is only available in the full regime.")
  }
  eta <- as.numeric(args$eta)
  delta <- as.numeric(s$beta_int) - as.numeric(s$beta_ext)
  db <- mainger::estimate_direction_biases(
    delta = delta,
    Sigma_int = as.matrix(s$Sigma_int),
    Sigma_ext = as.matrix(s$Sigma_ext),
    sigma2_ext = as.numeric(s$sigma2_ext),
    n_ext = as.integer(s$n_ext)
  )
  cc <- mainger::check_concordance(
    k_vals = db$k_vals, b_vals = db$b_vals,
    sigma2_int = as.numeric(s$sigma2_int),
    n_int = as.integer(s$n_int), eta = eta
  )
  adv <- mainger::spectral_advantage(
    k_vals = db$k_vals, b_vals = db$b_vals,
    sigma2_int = as.numeric(s$sigma2_int),
    n_int = as.integer(s$n_int), eta_grid = eta
  )

  # cc may be a string, named list, or structured object
  verdict <- if (is.character(cc)) cc[1]
             else if (is.list(cc) && !is.null(cc$verdict)) cc$verdict
             else as.character(cc)

  list(eta = eta,
       verdict = verdict,
       advantage = unname(adv)[1],
       k_vals = unname(db$k_vals),
       b_vals = unname(db$b_vals),
       raw = cc)
}

fit_integrated_estimator <- function(args, s) {
  fit_args <- list(
    X_int      = if (!is.null(s$X_int))     as.matrix(s$X_int) else NULL,
    Y_int      = if (!is.null(s$Y_int))     as.numeric(s$Y_int) else NULL,
    beta_int   = s$beta_int,
    Sigma_int  = if (!is.null(s$Sigma_int)) as.matrix(s$Sigma_int) else NULL,
    r_int      = s$r_int,
    Sigma_ref  = if (!is.null(s$Sigma_ref)) as.matrix(s$Sigma_ref) else NULL,
    beta_ext   = s$beta_ext,
    Sigma_ext  = if (!is.null(s$Sigma_ext)) as.matrix(s$Sigma_ext) else NULL,
    sigma2_int = s$sigma2_int,
    sigma2_ext = s$sigma2_ext,
    n_int      = s$n_int,
    n_ext      = s$n_ext,
    tuning     = args$tuning %||% "fixed",
    eta        = args$eta
  )
  fit_args <- fit_args[!vapply(fit_args, is.null, logical(1))]
  fit <- do.call(mainger::mainger, fit_args)

  pname <- s$predictor_names %||% paste0("x", seq_along(fit$coefficients))

  list(
    regime_detected = fit$scenario,
    eta_used   = unname(fit$eta %||% args$eta),
    eta_bound  = unname(fit$eta_bound %||% NA_real_),
    tuning_method = fit$tuning_method %||% (args$tuning %||% "fixed"),
    coef = setNames(as.list(unname(fit$coefficients)), pname),
    coef_internal = if (!is.null(fit$internal$beta))
                      setNames(as.list(unname(fit$internal$beta)), pname) else NULL,
    coef_external = if (!is.null(fit$external$beta))
                      setNames(as.list(unname(fit$external$beta)), pname) else NULL,
    diagnostics = fit$diagnostics
  )
}

# --- Dispatch -------------------------------------------------------------- #
out <- tryCatch({
  res <- switch(tool,
    detect_regime            = detect_regime(args, session),
    compute_eta_bound        = compute_eta_bound(args, session),
    check_concordance        = check_concordance(args, session),
    fit_integrated_estimator = fit_integrated_estimator(args, session),
    stop(sprintf("Unknown tool '%s'", tool))
  )
  list(ok = TRUE, result = res)
}, error = function(e) {
  list(ok = FALSE, error = conditionMessage(e))
})

cat(toJSON(out, auto_unbox = TRUE, null = "null", na = "null"))