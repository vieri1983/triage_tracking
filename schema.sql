bugs=> \d tBugs;
                                   Table "public.tbugs"
     Column      |       Type        |                     Modifiers                      
-----------------+-------------------+----------------------------------------------------
 id              | integer           | not null default nextval('tbugs_id_seq'::regclass)
 bug_id          | integer           | 
 summary         | character varying | 
 severity        | character varying | 
 priority        | character varying | 
 status          | character varying | 
 assignee        | character varying | 
 qa              | character varying | 
 product         | character varying | 
 category        | character varying | 
 component       | character varying | 
 fixby           | character varying | 
 resolvedatelong | boolean           | 
 triagedatelong  | boolean           | 
Indexes:
    "tbugs_pkey" PRIMARY KEY, btree (id)
