# llang-native machine learning module (no host-language bridge).
#
# Semantics follow scikit-learn 1.8.0 (BSD-3-Clause); formulas and default
# conventions are reproduced, no scikit-learn source is copied. Every estimator
# is a self-describing map with keys: version, kind, fitted, predict, parameters,
# state. The stored "predict" value is a llang function of (model, features), so
# the builtin `call predict with model = M, features = X` works on every model.
#
# Exports: split, standardize, transform, fit_linear, gradient, neighbours,
# cluster, kmeans, predict, accuracy, accuracy_count, mse, rmse, mae, r2,
# precision, recall, f1, confusion, f1_macro, f1_micro, f1_weighted, evaluate,
# report, distance, column.

use the math module

# --- shared validation and small helpers ------------------------------------

define function validate_rows taking rows
    if not (rows is a list) then
        fail with bad_features, "ml_error/bad_features: features must be a list of rows"
    end if
    if (the length of rows) is less than 1 then
        fail with empty_features, "ml_error/empty_features: features must contain at least one row"
    end if
    set width to the length of (item 0 of rows)
    if width is less than 1 then
        fail with empty_features, "ml_error/empty_features: each row must contain at least one value"
    end if
    repeat for each row in rows
        if not (row is a list) then
            fail with bad_features, "ml_error/bad_features: each row must be a list"
        end if
        if (the length of row) does not equal width then
            fail with inconsistent_width, "ml_error/inconsistent_width: rows must share one width"
        end if
        repeat for each value in row
            if value is nothing then
                fail with missing_value, "ml_error/missing_value: nothing is not a feature value"
            end if
            if not (value is a number) then
                fail with non_numeric_feature, "ml_error/non_numeric_feature: feature values must be numbers"
            end if
        end repeat
    end repeat
    give back width
end function

define function check_numeric_values taking number_list
    if not (number_list is a list) then
        fail with invalid_labels, "ml_error/invalid_labels: targets must be a list of numbers"
    end if
    if (the length of number_list) is less than 1 then
        fail with too_few_samples, "ml_error/too_few_samples: targets must not be empty"
    end if
    repeat for each value in number_list
        if not (value is a number) then
            fail with invalid_labels, "ml_error/invalid_labels: targets must be numbers"
        end if
    end repeat
    give back the length of number_list
end function

define function check_class_labels taking labels
    if not (labels is a list) then
        fail with invalid_labels, "ml_error/invalid_labels: labels must be a list"
    end if
    if (the length of labels) is less than 1 then
        fail with too_few_samples, "ml_error/too_few_samples: labels must not be empty"
    end if
    set first_label to item 0 of labels
    repeat for each label in labels
        if label is nothing then
            fail with invalid_labels, "ml_error/invalid_labels: nothing is not a label"
        end if
        set same_kind to false
        if (first_label is a number) and (label is a number) then
            set same_kind to true
        end if
        if (first_label is text) and (label is text) then
            set same_kind to true
        end if
        if ((first_label equals true) or (first_label equals false)) and ((label equals true) or (label equals false)) then
            set same_kind to true
        end if
        if not same_kind then
            fail with invalid_labels, "ml_error/invalid_labels: labels must all share one type"
        end if
    end repeat
    give back the length of labels
end function

define function whole taking value
    set pieces to call split text with text = (call text of with value = value), by = "."
    give back call to number with text = item 0 of pieces
end function

define function copy_row taking row
    set fresh to an empty list
    repeat for each value in row
        add value to fresh
    end repeat
    give back fresh
end function

define function dot taking left, right
    set total to 0
    set i to 0
    repeat while i is less than (the length of left)
        set total to total plus ((item i of left) times (item i of right))
        set i to i plus 1
    end repeat
    give back total
end function

define function squared_distance taking left, right
    set total to 0
    set i to 0
    repeat while i is less than (the length of left)
        set diff to (item i of left) minus (item i of right)
        set total to total plus (diff times diff)
        set i to i plus 1
    end repeat
    give back total
end function

define function distance taking left, right
    if (not (left is a list)) or (not (right is a list)) then
        fail with bad_features, "ml_error/bad_features: distance needs two numeric lists"
    end if
    if (the length of left) does not equal (the length of right) then
        fail with inconsistent_width, "ml_error/inconsistent_width: distance needs equal widths"
    end if
    give back call sqrt from math with value = (call squared_distance with left = left, right = right)
end function

define function column taking rows, index
    call validate_rows with rows = rows
    set width to the length of (item 0 of rows)
    if (index is less than 0) or (index is at least width) then
        fail with index_out_of_range, "ml_error/index_out_of_range: column index is out of range"
    end if
    set result to an empty list
    repeat for each row in rows
        add item index of row to result
    end repeat
    give back result
end function

define function less_value taking left, right
    if (left is a number) and (right is a number) then
        give back left is less than right
    end if
    if (left is text) and (right is text) then
        give back left is less than right
    end if
    set left_code to 0
    set right_code to 0
    if left equals true then
        set left_code to 1
    end if
    if right equals true then
        set right_code to 1
    end if
    give back left_code is less than right_code
end function

define function sorted_unique taking labels
    set classes to an empty list
    repeat for each label in labels
        if not (call contains with collection = classes, value = label) then
            add label to classes
        end if
    end repeat
    set i to 1
    repeat while i is less than (the length of classes)
        set key to item i of classes
        set j to i minus 1
        repeat while j is at least 0
            if call less_value with left = key, right = (item j of classes) then
                set item (j plus 1) of classes to item j of classes
                set j to j minus 1
            otherwise
                stop the loop
            end if
        end repeat
        set item (j plus 1) of classes to key
        set i to i plus 1
    end repeat
    give back classes
end function

define function build_model taking model_kind, params, state
    give back a map with "version" mapped to 1, "kind" mapped to model_kind, "fitted" mapped to true, "predict" mapped to predict, "parameters" mapped to params, "state" mapped to state
end function

# --- data preparation -------------------------------------------------------

define function split taking features, labels, test_size, seed
    call validate_rows with rows = features
    set n to the length of features
    if n is less than 2 then
        fail with too_few_samples, "ml_error/too_few_samples: split needs at least two samples"
    end if
    if (the length of labels) does not equal n then
        fail with length_mismatch, "ml_error/length_mismatch: features and labels must align"
    end if
    if (not (test_size is a number)) or (test_size is at most 0) or (test_size is at least 1) then
        fail with bad_test_size, "ml_error/bad_test_size: test_size must be a fraction strictly between 0 and 1"
    end if
    set wanted to n times test_size
    set test_count to 0
    repeat while test_count is less than wanted
        set test_count to test_count plus 1
    end repeat
    set train_count to n minus test_count
    if (train_count is less than 1) or (test_count is less than 1) then
        fail with too_few_samples, "ml_error/too_few_samples: split produced an empty side"
    end if
    set indices to an empty list
    set i to 0
    repeat while i is less than n
        add i to indices
        set i to i plus 1
    end repeat
    set state to call whole with value = seed
    set i to n minus 1
    repeat while i is greater than 0
        set state to (state times 1103515245 plus 12345) modulo 2147483648
        set pos to state modulo (i plus 1)
        set tmp to item i of indices
        set item i of indices to item pos of indices
        set item pos of indices to tmp
        set i to i minus 1
    end repeat
    set train_features to an empty list
    set test_features to an empty list
    set train_labels to an empty list
    set test_labels to an empty list
    repeat for each idx in indices
        if (the length of train_features) is less than train_count then
            add call copy_row with row = (item idx of features) to train_features
            add item idx of labels to train_labels
        otherwise
            add call copy_row with row = (item idx of features) to test_features
            add item idx of labels to test_labels
        end if
    end repeat
    give back a map with "train_features" mapped to train_features, "test_features" mapped to test_features, "train_labels" mapped to train_labels, "test_labels" mapped to test_labels
end function

define function standardize taking features, with_mean, with_std
    set width to call validate_rows with rows = features
    set n to the length of features
    set means to an empty list
    set scales to an empty list
    set j to 0
    repeat while j is less than width
        set total to 0
        repeat for each row in features
            set total to total plus (item j of row)
        end repeat
        set mean_value to total divided by n
        if with_mean then
            add mean_value to means
        otherwise
            add 0 to means
        end if
        if with_std then
            set sum_sq to 0
            repeat for each row in features
                set diff to (item j of row) minus mean_value
                set sum_sq to sum_sq plus (diff times diff)
            end repeat
            set scale_value to call sqrt from math with value = (sum_sq divided by n)
            if scale_value equals 0 then
                set scale_value to 1
            end if
            add scale_value to scales
        otherwise
            add 1 to scales
        end if
        set j to j plus 1
    end repeat
    set params to a map with "with_mean" mapped to with_mean, "with_std" mapped to with_std
    set state to a map with "mean" mapped to means, "scale" mapped to scales
    give back call build_model with model_kind = "standardizer", params = params, state = state
end function

define function transform taking model, features
    if not (model is a map) then
        fail with wrong_model_kind, "ml_error/wrong_model_kind: transform needs a model map"
    end if
    set model_kind to item "kind" of model
    if model_kind does not equal "standardizer" then
        fail with wrong_model_kind, "ml_error/wrong_model_kind: transform needs a standardizer map"
    end if
    set fitted to item "fitted" of model
    if not (fitted equals true) then
        fail with not_fitted, "ml_error/not_fitted: the scaler has not been fitted"
    end if
    set state to item "state" of model
    set means to item "mean" of state
    set scales to item "scale" of state
    set width to call validate_rows with rows = features
    if width does not equal (the length of means) then
        fail with inconsistent_width, "ml_error/inconsistent_width: features must match the fitted width"
    end if
    set result to an empty list
    repeat for each row in features
        set fresh to an empty list
        set j to 0
        repeat while j is less than width
            set shifted to ((item j of row) minus (item j of means)) divided by (item j of scales)
            add shifted to fresh
            set j to j plus 1
        end repeat
        add fresh to result
    end repeat
    give back result
end function

# --- regression -------------------------------------------------------------

define function fit_linear taking features, targets, fit_intercept
    set width to call validate_rows with rows = features
    set count to call check_numeric_values with number_list = targets
    if count does not equal (the length of features) then
        fail with length_mismatch, "ml_error/length_mismatch: features and targets must align"
    end if
    set columns to width
    if fit_intercept then
        set columns to columns plus 1
    end if
    set design to an empty list
    repeat for each row in features
        set fresh to an empty list
        if fit_intercept then
            add 1 to fresh
        end if
        repeat for each value in row
            add value to fresh
        end repeat
        add fresh to design
    end repeat
    set normal to an empty list
    set r to 0
    repeat while r is less than columns
        set fresh to an empty list
        set c to 0
        repeat while c is less than (columns plus 1)
            set total to 0
            set k to 0
            repeat while k is less than count
                if c is less than columns then
                    set total to total plus ((item r of (item k of design)) times (item c of (item k of design)))
                otherwise
                    set total to total plus ((item r of (item k of design)) times (item k of targets))
                end if
                set k to k plus 1
            end repeat
            add total to fresh
            set c to c plus 1
        end repeat
        add fresh to normal
        set r to r plus 1
    end repeat
    # A tiny diagonal ridge reproduces the minimum-norm SVD solution on
    # rank-deficient designs while leaving full-rank coefficients unchanged.
    set max_diag to 0
    set r to 0
    repeat while r is less than columns
        set diagonal to call absolute with value = item r of (item r of normal)
        if diagonal is greater than max_diag then
            set max_diag to diagonal
        end if
        set r to r plus 1
    end repeat
    set ridge to max_diag times 0.0000000001
    set r to 0
    repeat while r is less than columns
        set item r of (item r of normal) to (item r of (item r of normal)) plus ridge
        set r to r plus 1
    end repeat
    set col to 0
    repeat while col is less than columns
        set pivot_row to col
        set best to call absolute with value = item col of (item col of normal)
        set r to col plus 1
        repeat while r is less than columns
            set candidate to call absolute with value = item col of (item r of normal)
            if candidate is greater than best then
                set best to candidate
                set pivot_row to r
            end if
            set r to r plus 1
        end repeat
        if best is less than 0.000000000001 then
            fail with singular_matrix, "ml_error/singular_matrix: the design matrix is singular"
        end if
        if pivot_row does not equal col then
            set tmp to item col of normal
            set item col of normal to item pivot_row of normal
            set item pivot_row of normal to tmp
        end if
        set pivot to item col of (item col of normal)
        set r to col plus 1
        repeat while r is less than columns
            set factor to (item col of (item r of normal)) divided by pivot
            set c to col
            repeat while c is less than (columns plus 1)
                set item c of (item r of normal) to (item c of (item r of normal)) minus (factor times (item c of (item col of normal)))
                set c to c plus 1
            end repeat
            set r to r plus 1
        end repeat
        set col to col plus 1
    end repeat
    set solution to an empty list
    set i to 0
    repeat while i is less than columns
        add 0 to solution
        set i to i plus 1
    end repeat
    set r to columns minus 1
    repeat while r is at least 0
        set total to item columns of (item r of normal)
        set c to r plus 1
        repeat while c is less than columns
            set total to total minus ((item c of (item r of normal)) times (item c of solution))
            set c to c plus 1
        end repeat
        set item r of solution to total divided by (item r of (item r of normal))
        set r to r minus 1
    end repeat
    set coefficients to an empty list
    set intercept to 0
    set i to 0
    repeat while i is less than columns
        if (fit_intercept equals false) or (i is greater than 0) then
            add item i of solution to coefficients
        otherwise
            set intercept to item i of solution
        end if
        set i to i plus 1
    end repeat
    set params to a map with "fit_intercept" mapped to fit_intercept
    set state to a map with "coefficients" mapped to coefficients, "intercept" mapped to intercept
    give back call build_model with model_kind = "linear_regression", params = params, state = state
end function

define function gradient taking features, targets, rate, steps, fit_intercept
    set width to call validate_rows with rows = features
    set count to call check_numeric_values with number_list = targets
    if count does not equal (the length of features) then
        fail with length_mismatch, "ml_error/length_mismatch: features and targets must align"
    end if
    set rounds to call whole with value = steps
    if rounds is less than 1 then
        fail with bad_steps, "ml_error/bad_steps: steps must be a positive whole number"
    end if
    set coefficients to an empty list
    set j to 0
    repeat while j is less than width
        add 0 to coefficients
        set j to j plus 1
    end repeat
    set intercept to 0
    set scale to 2 divided by count
    set step to 0
    repeat while step is less than rounds
        set grads to an empty list
        set j to 0
        repeat while j is less than width
            add 0 to grads
            set j to j plus 1
        end repeat
        set grad_intercept to 0
        set i to 0
        repeat while i is less than count
            set estimate to intercept
            set j to 0
            repeat while j is less than width
                set estimate to estimate plus ((item j of coefficients) times (item j of (item i of features)))
                set j to j plus 1
            end repeat
            set residual to (item i of targets) minus estimate
            set grad_intercept to grad_intercept plus residual
            set j to 0
            repeat while j is less than width
                set item j of grads to (item j of grads) plus (residual times (item j of (item i of features)))
                set j to j plus 1
            end repeat
            set i to i plus 1
        end repeat
        set j to 0
        repeat while j is less than width
            set item j of coefficients to (item j of coefficients) plus (rate times scale times (item j of grads))
            set j to j plus 1
        end repeat
        if fit_intercept then
            set intercept to intercept plus (rate times scale times grad_intercept)
        end if
        set step to step plus 1
    end repeat
    set params to a map with "fit_intercept" mapped to fit_intercept, "rate" mapped to rate, "steps" mapped to steps
    set state to a map with "coefficients" mapped to coefficients, "intercept" mapped to intercept
    give back call build_model with model_kind = "linear_regression", params = params, state = state
end function

# --- clustering -------------------------------------------------------------

define function squared_distance_map taking row, centers
    set best to call squared_distance with left = row, right = (item 0 of centers)
    set winner to 0
    set j to 1
    repeat while j is less than (the length of centers)
        set candidate to call squared_distance with left = row, right = (item j of centers)
        if candidate is less than best then
            set best to candidate
            set winner to j
        end if
        set j to j plus 1
    end repeat
    give back a map with "distance" mapped to best, "winner" mapped to winner
end function

define function assign_centers taking features, centers
    set labels to an empty list
    set inertia to 0
    repeat for each row in features
        set best to call squared_distance_map with row = row, centers = centers
        add item "winner" of best to labels
        set inertia to inertia plus (item "distance" of best)
    end repeat
    give back a map with "labels" mapped to labels, "inertia" mapped to inertia
end function

define function choose_centers taking features, clusters, seed, init
    set n to the length of features
    if init equals "first_rows" then
        set first_centers to an empty list
        set c to 0
        repeat while c is less than clusters
            add call copy_row with row = (item c of features) to first_centers
            set c to c plus 1
        end repeat
        give back first_centers
    end if
    if init does not equal "kmeans_plus_plus" then
        fail with bad_init, "ml_error/bad_init: init must be kmeans_plus_plus or first_rows"
    end if
    set state to call whole with value = seed
    set centers to an empty list
    set state to (state times 1103515245 plus 12345) modulo 2147483648
    set idx to state modulo n
    add call copy_row with row = (item idx of features) to centers
    set c to 1
    repeat while c is less than clusters
        set weights to an empty list
        set total to 0
        repeat for each row in features
            set best to call squared_distance_map with row = row, centers = centers
            set value to item "distance" of best
            add value to weights
            set total to total plus value
        end repeat
        if total equals 0 then
            set idx to state modulo n
        otherwise
            set state to (state times 1103515245 plus 12345) modulo 2147483648
            set target to (state divided by 2147483648) times total
            set cumulative to 0
            set idx to n minus 1
            set i to 0
            repeat while i is less than n
                set cumulative to cumulative plus (item i of weights)
                if cumulative is at least target then
                    set idx to i
                    stop the loop
                end if
                set i to i plus 1
            end repeat
        end if
        add call copy_row with row = (item idx of features) to centers
        set c to c plus 1
    end repeat
    give back centers
end function

define function kmeans taking features, clusters, seed, restarts, init
    set width to call validate_rows with rows = features
    set n to the length of features
    if (not (clusters is a number)) or (clusters is less than 1) then
        fail with too_many_clusters, "ml_error/too_many_clusters: clusters must be positive"
    end if
    if clusters is greater than n then
        fail with too_many_clusters, "ml_error/too_many_clusters: clusters exceeds the number of rows"
    end if
    set repeats to call whole with value = restarts
    if repeats is less than 1 then
        fail with bad_restarts, "ml_error/bad_restarts: restarts must be positive"
    end if
    set best_score to 0 minus 1
    set best_centers to an empty list
    set best_labels to an empty list
    set run to 0
    repeat while run is less than repeats
        set run_seed to (call whole with value = seed) plus (run times 7919)
        set centers to call choose_centers with features = features, clusters = clusters, seed = run_seed, init = init
        set iteration to 0
        repeat while iteration is less than 100
            set assigned to call assign_centers with features = features, centers = centers
            set fresh_centers to an empty list
            set c to 0
            repeat while c is less than clusters
                set accumulator to an empty list
                set j to 0
                repeat while j is less than width
                    add 0 to accumulator
                    set j to j plus 1
                end repeat
                set total_count to 0
                set i to 0
                repeat while i is less than n
                    if (item i of (item "labels" of assigned)) equals c then
                        set j to 0
                        repeat while j is less than width
                            set item j of accumulator to (item j of accumulator) plus (item j of (item i of features))
                            set j to j plus 1
                        end repeat
                        set total_count to total_count plus 1
                    end if
                    set i to i plus 1
                end repeat
                set fresh_center to an empty list
                if total_count equals 0 then
                    set fallback to run_seed modulo n
                    set fresh_center to call copy_row with row = (item fallback of features)
                otherwise
                    set j to 0
                    repeat while j is less than width
                        add (item j of accumulator) divided by total_count to fresh_center
                        set j to j plus 1
                    end repeat
                end if
                add fresh_center to fresh_centers
                set c to c plus 1
            end repeat
            set movement to 0
            set c to 0
            repeat while c is less than clusters
                set j to 0
                repeat while j is less than width
                    set delta to (item j of (item c of centers)) minus (item j of (item c of fresh_centers))
                    set magnitude to call absolute with value = delta
                    if magnitude is greater than movement then
                        set movement to magnitude
                    end if
                    set j to j plus 1
                end repeat
                set c to c plus 1
            end repeat
            set centers to fresh_centers
            set iteration to iteration plus 1
            if movement is less than 0.0000000001 then
                stop the loop
            end if
        end repeat
        set assigned to call assign_centers with features = features, centers = centers
        set inertia to item "inertia" of assigned
        if (best_score is less than 0) or (inertia is less than best_score) then
            set best_score to inertia
            set best_centers to centers
            set best_labels to item "labels" of assigned
        end if
        set run to run plus 1
    end repeat
    set params to a map with "clusters" mapped to clusters, "seed" mapped to seed, "restarts" mapped to restarts, "init" mapped to init
    set state to a map with "centers" mapped to best_centers, "labels" mapped to best_labels, "inertia" mapped to best_score
    give back call build_model with model_kind = "k_means", params = params, state = state
end function

define function cluster taking features, clusters
    give back call kmeans with features = features, clusters = clusters, seed = 0, restarts = 10, init = "kmeans_plus_plus"
end function

# --- nearest neighbours -----------------------------------------------------

define function neighbours taking features, labels, k, task, weights, seed
    call validate_rows with rows = features
    set n to the length of features
    call check_class_labels with labels = labels
    if (the length of labels) does not equal n then
        fail with length_mismatch, "ml_error/length_mismatch: features and labels must align"
    end if
    set count to call whole with value = k
    if count is less than 1 then
        fail with bad_k, "ml_error/bad_k: k must be at least 1"
    end if
    if count is greater than n then
        fail with too_many_neighbors, "ml_error/too_many_neighbors: k exceeds the number of training rows"
    end if
    if (task does not equal "classify") and (task does not equal "regress") then
        fail with bad_task, "ml_error/bad_task: task must be classify or regress"
    end if
    if (weights does not equal "uniform") and (weights does not equal "distance") then
        fail with bad_weights, "ml_error/bad_weights: weights must be uniform or distance"
    end if
    set examples to an empty list
    repeat for each row in features
        add call copy_row with row = row to examples
    end repeat
    set saved_labels to an empty list
    repeat for each label in labels
        add label to saved_labels
    end repeat
    set classes to call sorted_unique with labels = saved_labels
    set params to a map with "k" mapped to k, "task" mapped to task, "weights" mapped to weights, "seed" mapped to seed
    set state to a map with "examples" mapped to examples, "labels" mapped to saved_labels, "classes" mapped to classes
    give back call build_model with model_kind = "k_neighbors", params = params, state = state
end function

define function nearest_order taking row, examples
    set distances to an empty list
    set n to the length of examples
    set i to 0
    repeat while i is less than n
        add call distance with left = row, right = (item i of examples) to distances
        set i to i plus 1
    end repeat
    set order to an empty list
    set i to 0
    repeat while i is less than n
        add i to order
        set i to i plus 1
    end repeat
    set i to 1
    repeat while i is less than n
        set key to item i of order
        set j to i minus 1
        repeat while j is at least 0
            set left_distance to item (item j of order) of distances
            set key_distance to item key of distances
            if key_distance is less than left_distance then
                set item (j plus 1) of order to item j of order
                set j to j minus 1
            otherwise
                stop the loop
            end if
        end repeat
        set item (j plus 1) of order to key
        set i to i plus 1
    end repeat
    give back a map with "order" mapped to order, "distances" mapped to distances
end function

define function predict_neighbours taking model, features
    set state to item "state" of model
    set examples to item "examples" of state
    set saved_labels to item "labels" of state
    set classes to item "classes" of state
    set params to item "parameters" of model
    set count to call whole with value = item "k" of params
    set task to item "task" of params
    set weights to item "weights" of params
    set width to call validate_rows with rows = features
    if width does not equal (the length of (item 0 of examples)) then
        fail with inconsistent_width, "ml_error/inconsistent_width: features must match the training width"
    end if
    set result to an empty list
    repeat for each row in features
        set near to call nearest_order with row = row, examples = examples
        set order to item "order" of near
        set distances to item "distances" of near
        set has_zero to false
        set t to 0
        repeat while t is less than count
            if (item (item t of order) of distances) equals 0 then
                set has_zero to true
            end if
            set t to t plus 1
        end repeat
        if task equals "classify" then
            set tally to an empty list
            set c to 0
            repeat while c is less than (the length of classes)
                add 0 to tally
                set c to c plus 1
            end repeat
            set t to 0
            repeat while t is less than count
                set idx to item t of order
                set d to item idx of distances
                set weight to 1
                if weights equals "distance" then
                    if has_zero then
                        if d equals 0 then
                            set weight to 1
                        otherwise
                            set weight to 0
                        end if
                    otherwise
                        set weight to 1 divided by d
                    end if
                end if
                set label to item idx of saved_labels
                set c to 0
                repeat while c is less than (the length of classes)
                    if (item c of classes) equals label then
                        set item c of tally to (item c of tally) plus weight
                        stop the loop
                    end if
                    set c to c plus 1
                end repeat
                set t to t plus 1
            end repeat
            set best to item 0 of tally
            set winner to 0
            set c to 1
            repeat while c is less than (the length of classes)
                if (item c of tally) is greater than best then
                    set best to item c of tally
                    set winner to c
                end if
                set c to c plus 1
            end repeat
            add item winner of classes to result
        otherwise
            set total to 0
            set weight_total to 0
            set t to 0
            repeat while t is less than count
                set idx to item t of order
                set d to item idx of distances
                set weight to 1
                if weights equals "distance" then
                    if has_zero then
                        if d equals 0 then
                            set weight to 1
                        otherwise
                            set weight to 0
                        end if
                    otherwise
                        set weight to 1 divided by d
                    end if
                end if
                set total to total plus (weight times (item idx of saved_labels))
                set weight_total to weight_total plus weight
                set t to t plus 1
            end repeat
            if weight_total equals 0 then
                add 0 to result
            otherwise
                add total divided by weight_total to result
            end if
        end if
    end repeat
    give back result
end function

define function predict_centers taking model, features
    set state to item "state" of model
    set centers to item "centers" of state
    call validate_rows with rows = features
    set result to an empty list
    repeat for each row in features
        set best to call squared_distance_map with row = row, centers = centers
        add item "winner" of best to result
    end repeat
    give back result
end function

# --- dispatch ---------------------------------------------------------------

define function predict taking model, features
    if not (model is a map) then
        fail with not_fitted, "ml_error/not_fitted: predict needs a model map"
    end if
    set fitted to item "fitted" of model
    if not (fitted equals true) then
        fail with not_fitted, "ml_error/not_fitted: the model has not been fitted"
    end if
    set model_kind to item "kind" of model
    if model_kind equals "standardizer" then
        give back call transform with model = model, features = features
    end if
    if model_kind equals "linear_regression" then
        set state to item "state" of model
        set coefficients to item "coefficients" of state
        set intercept to item "intercept" of state
        set width to call validate_rows with rows = features
        if width does not equal (the length of coefficients) then
            fail with inconsistent_width, "ml_error/inconsistent_width: features must match the fitted width"
        end if
        set result to an empty list
        repeat for each row in features
            add (call dot with left = coefficients, right = row) plus intercept to result
        end repeat
        give back result
    end if
    if model_kind equals "k_neighbors" then
        give back call predict_neighbours with model = model, features = features
    end if
    if model_kind equals "k_means" then
        give back call predict_centers with model = model, features = features
    end if
    fail with unknown_model_kind, "ml_error/unknown_model_kind: unrecognised model kind"
end function

# --- metrics ----------------------------------------------------------------

define function check_metric_input taking actual, predicted
    if (not (actual is a list)) or (not (predicted is a list)) then
        fail with bad_metric_input, "ml_error/bad_metric_input: metrics need two lists"
    end if
    if ((the length of actual) is less than 1) or ((the length of actual) does not equal (the length of predicted)) then
        fail with bad_metric_input, "ml_error/bad_metric_input: metric lists must be non-empty and equal in length"
    end if
    give back the length of actual
end function

define function check_metric_values taking actual, predicted
    set n to call check_metric_input with actual = actual, predicted = predicted
    repeat for each value in actual
        if not (value is a number) then
            fail with bad_metric_input, "ml_error/bad_metric_input: regression metrics need numeric values"
        end if
    end repeat
    repeat for each value in predicted
        if not (value is a number) then
            fail with bad_metric_input, "ml_error/bad_metric_input: regression metrics need numeric values"
        end if
    end repeat
    give back n
end function

define function accuracy taking actual, predicted
    set n to call check_metric_input with actual = actual, predicted = predicted
    set correct to 0
    set i to 0
    repeat while i is less than n
        if (item i of actual) equals (item i of predicted) then
            set correct to correct plus 1
        end if
        set i to i plus 1
    end repeat
    give back correct divided by n
end function

define function accuracy_count taking actual, predicted
    set n to call check_metric_input with actual = actual, predicted = predicted
    set correct to 0
    set i to 0
    repeat while i is less than n
        if (item i of actual) equals (item i of predicted) then
            set correct to correct plus 1
        end if
        set i to i plus 1
    end repeat
    give back correct plus 0.0
end function

define function mse taking actual, predicted
    set n to call check_metric_values with actual = actual, predicted = predicted
    set total to 0
    set i to 0
    repeat while i is less than n
        set diff to (item i of actual) minus (item i of predicted)
        set total to total plus (diff times diff)
        set i to i plus 1
    end repeat
    give back total divided by n
end function

define function rmse taking actual, predicted
    set value to call mse with actual = actual, predicted = predicted
    give back call sqrt from math with value = value
end function

define function mae taking actual, predicted
    set n to call check_metric_values with actual = actual, predicted = predicted
    set total to 0
    set i to 0
    repeat while i is less than n
        set diff to (item i of actual) minus (item i of predicted)
        set total to total plus (call absolute with value = diff)
        set i to i plus 1
    end repeat
    give back total divided by n
end function

define function r2 taking actual, predicted
    set n to call check_metric_values with actual = actual, predicted = predicted
    if n is less than 2 then
        fail with bad_metric_input, "ml_error/bad_metric_input: r2 needs at least two rows"
    end if
    set mean_actual to (call sum with items = actual) divided by n
    set total_ss to 0
    set residual_ss to 0
    set i to 0
    repeat while i is less than n
        set centered to (item i of actual) minus mean_actual
        set residual to (item i of actual) minus (item i of predicted)
        set total_ss to total_ss plus (centered times centered)
        set residual_ss to residual_ss plus (residual times residual)
        set i to i plus 1
    end repeat
    if total_ss equals 0 then
        if residual_ss equals 0 then
            give back 1
        end if
        give back 0
    end if
    give back 1 minus (residual_ss divided by total_ss)
end function

define function binary_counts taking actual, predicted, positive
    set n to call check_metric_input with actual = actual, predicted = predicted
    set true_positive to 0
    set false_positive to 0
    set false_negative to 0
    set i to 0
    repeat while i is less than n
        set is_actual to (item i of actual) equals positive
        set is_guess to (item i of predicted) equals positive
        if is_actual and is_guess then
            set true_positive to true_positive plus 1
        end if
        if (not is_actual) and is_guess then
            set false_positive to false_positive plus 1
        end if
        if is_actual and (not is_guess) then
            set false_negative to false_negative plus 1
        end if
        set i to i plus 1
    end repeat
    give back a map with "tp" mapped to true_positive, "fp" mapped to false_positive, "fn" mapped to false_negative
end function

define function precision taking actual, predicted, positive
    set counts to call binary_counts with actual = actual, predicted = predicted, positive = positive
    set denominator to (item "tp" of counts) plus (item "fp" of counts)
    if denominator equals 0 then
        give back 0.0
    end if
    give back (item "tp" of counts) divided by denominator
end function

define function recall taking actual, predicted, positive
    set counts to call binary_counts with actual = actual, predicted = predicted, positive = positive
    set denominator to (item "tp" of counts) plus (item "fn" of counts)
    if denominator equals 0 then
        give back 0.0
    end if
    give back (item "tp" of counts) divided by denominator
end function

define function f1 taking actual, predicted, positive
    set p to call precision with actual = actual, predicted = predicted, positive = positive
    set r to call recall with actual = actual, predicted = predicted, positive = positive
    set denominator to p plus r
    if denominator equals 0 then
        give back 0.0
    end if
    give back 2 times p times r divided by denominator
end function

define function confusion taking actual, predicted, classes
    set n to call check_metric_input with actual = actual, predicted = predicted
    set result to an empty map
    repeat for each label_value in classes
        set row to an empty list
        set j to 0
        repeat while j is less than (the length of classes)
            add 0 to row
            set j to j plus 1
        end repeat
        set item (call text of with value = label_value) of result to row
    end repeat
    set i to 0
    repeat while i is less than n
        set actual_class to item i of actual
        set guess_class to item i of predicted
        set found_actual to false
        set found_guess to false
        set j to 0
        repeat while j is less than (the length of classes)
            if (item j of classes) equals actual_class then
                set found_actual to true
            end if
            if (item j of classes) equals guess_class then
                set found_guess to true
            end if
            set j to j plus 1
        end repeat
        if (not found_actual) or (not found_guess) then
            fail with invalid_labels, "ml_error/invalid_labels: confusion needs every label listed in classes"
        end if
        # find the offsets of both classes within the supplied list
        set actual_pos to 0
        set guess_pos to 0
        set j to 0
        repeat while j is less than (the length of classes)
            if (item j of classes) equals actual_class then
                set actual_pos to j
            end if
            if (item j of classes) equals guess_class then
                set guess_pos to j
            end if
            set j to j plus 1
        end repeat
        set target_row to item (call text of with value = actual_class) of result
        set item guess_pos of target_row to (item guess_pos of target_row) plus 1
        set i to i plus 1
    end repeat
    give back result
end function

define function f1_macro taking actual, predicted
    set classes to call sorted_unique with labels = actual
    repeat for each label in predicted
        if not (call contains with collection = classes, value = label) then
            add label to classes
        end if
    end repeat
    set classes to call sorted_unique with labels = classes
    if (the length of classes) equals 0 then
        fail with bad_metric_input, "ml_error/bad_metric_input: metrics need labels"
    end if
    set total to 0
    repeat for each label in classes
        set total to total plus (call f1 with actual = actual, predicted = predicted, positive = label)
    end repeat
    give back total divided by (the length of classes)
end function

define function f1_micro taking actual, predicted
    give back call accuracy with actual = actual, predicted = predicted
end function

define function f1_weighted taking actual, predicted
    set classes to call sorted_unique with labels = actual
    repeat for each label in predicted
        if not (call contains with collection = classes, value = label) then
            add label to classes
        end if
    end repeat
    set classes to call sorted_unique with labels = classes
    set n to call check_metric_input with actual = actual, predicted = predicted
    set total to 0
    repeat for each label in classes
        set support to 0
        repeat for each value in actual
            if value equals label then
                set support to support plus 1
            end if
        end repeat
        set total to total plus (support times (call f1 with actual = actual, predicted = predicted, positive = label))
    end repeat
    give back total divided by n
end function

# --- workflows --------------------------------------------------------------

define function evaluate taking model, features, actual
    if not (model is a map) then
        fail with wrong_model_kind, "ml_error/wrong_model_kind: evaluate needs a model map"
    end if
    set model_kind to item "kind" of model
    if model_kind equals "k_means" then
        set state to item "state" of model
        give back a map with "inertia" mapped to item "inertia" of state, "centers" mapped to item "centers" of state
    end if
    if (model_kind does not equal "linear_regression") and (model_kind does not equal "k_neighbors") then
        fail with wrong_model_kind, "ml_error/wrong_model_kind: evaluate does not support this model kind"
    end if
    set guesses to call predict with model = model, features = features
    if model_kind equals "linear_regression" then
        give back a map with "mse" mapped to (call mse with actual = actual, predicted = guesses), "rmse" mapped to (call rmse with actual = actual, predicted = guesses), "mae" mapped to (call mae with actual = actual, predicted = guesses), "r2" mapped to (call r2 with actual = actual, predicted = guesses)
    end if
    set state to item "state" of model
    set classes to item "classes" of state
    set positive to item ((the length of classes) minus 1) of classes
    give back a map with "accuracy" mapped to (call accuracy with actual = actual, predicted = guesses), "precision" mapped to (call precision with actual = actual, predicted = guesses, positive = positive), "recall" mapped to (call recall with actual = actual, predicted = guesses, positive = positive), "f1" mapped to (call f1 with actual = actual, predicted = guesses, positive = positive), "confusion" mapped to (call confusion with actual = actual, predicted = guesses, classes = classes)
end function

define function report taking scores
    if not (scores is a map) then
        fail with bad_scores, "ml_error/bad_scores: report needs a scores map"
    end if
    set names to call keys of with collection = scores
    set line to ""
    set i to 0
    repeat while i is less than (the length of names)
        set name to item i of names
        set value to item name of scores
        if value is a number then
            set piece to name plus "=" plus (call text of with value = (call rounded to places with value = value, places = 6))
        otherwise
            set piece to name plus "=" plus (call text of with value = value)
        end if
        if i is greater than 0 then
            set line to line plus " "
        end if
        set line to line plus piece
        set i to i plus 1
    end repeat
    give back line
end function
