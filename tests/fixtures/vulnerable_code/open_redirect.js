// EXPECTED: CWE-601, Open Redirect, line 18, severity: high

const express = require('express');
const router = express.Router();

/**
 * Authentication callback handler.
 * After login, redirects user to the requested page.
 */
router.get('/auth/callback', (req, res) => {
    const { token, redirect_url } = req.query;

    if (!token) {
        return res.status(400).send('Missing token');
    }

    // Vulnerable: redirects to any URL without validation
    res.redirect(redirect_url || '/dashboard');
});

/**
 * Logout handler with redirect.
 */
router.get('/logout', (req, res) => {
    req.session.destroy();
    // Also vulnerable: uses user-supplied next parameter
    const next = req.query.next;
    res.redirect(next || '/');
});

/**
 * Short URL redirector.
 */
router.get('/go/:target', (req, res) => {
    const target = decodeURIComponent(req.params.target);
    // No validation that target is an internal URL
    res.redirect(302, target);
});

module.exports = router;
