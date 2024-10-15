-- 1 userid to many accountid
CREATE TABLE registrations (
    userid character varying(64) NOT NULL,
    accountid character varying(32) NOT NULL
);

CREATE TABLE fraudulent_accounts (
    accountid character varying(32) NOT NULL,
    fraud_type character varying(32) NOT NULL -- enum maybe of type of fraud?
);

CREATE TABLE users (
    userid character varying(64) NOT NULL
    -- how can this be populated by web server after google sso auth
    -- shared attribs like name, email, etc?
);






