parserfrom __future__ import print_function
from pyspark import SparkConf, SparkContext
from pyspark.sql import SQLContext
from pyspark.sql.functions import *
from pyspark.sql.types import *

# IMPORT OTHER MODULES HERE
from pyspark.ml.feature import CountVectorizer
from pyspark.ml.feature import CountVectorizerModel
# Bunch of imports (may need more)
from pyspark.ml.classification import LogisticRegression
from pyspark.ml.tuning import CrossValidator, ParamGridBuilder
from pyspark.ml.tuning import CrossValidatorModel
from pyspark.ml.evaluation import BinaryClassificationEvaluator
import os

def dem(context):
    #TASK 1

    # Read from JSON
    #comments = sqlContext.read.json("comments-minimal.json.bz2")
    #comments.registerTempTable("commentsTable")
    #submissions = sqlContext.read.json("submissions.json.bz2")
    #submissions.registerTempTable("submissionsTable")

    # Write the Parquets
    #comments.write.parquet("comments.parquet")
    #submissions.write.parquet("submissions.parquet")

    # Read the parquets
    comments = sqlContext.read.parquet("comments.parquet")
    comments.registerTempTable("commentsTable")
    submissions = sqlContext.read.parquet("submissions.parquet")
    submissions.registerTempTable("submissionsTable")

    # Read the CSV
    labels = sqlContext.read.format('csv').options(header='true', inferSchema='true').load("labeled_data.csv")
    labels.registerTempTable("labelsTable")

    #TASK 2
    dfTask2 = sqlContext.sql("SELECT commentsTable.* FROM commentsTable INNER JOIN labelsTable ON commentsTable.id = labelsTable.Input_id")

    #TASK 4 and TASK 5
    def do_something(text):
        return parser.sanitize(text)

    udf_func = udf(do_something, ArrayType(StringType()))
    dfTask4 = dfTask2.withColumn("udf_results", udf_func(col("body")))

    #TASK 6A and Task 6B
    if(not os.path.exists("cvModel")):
        cv = CountVectorizer(inputCol="udf_results", outputCol="features", binary=True, minDF=5.0)
        model = cv.fit(dfTask4)
        model.write().overwrite().save("cvModel")

    model = CountVectorizerModel.load("cvModel")
    dfTask6A = model.transform(dfTask4)
    dfTask6A.registerTempTable("dfTask6ATable")
    dfTask6B = sqlContext.sql("SELECT dfTask6ATable.*, IF(labelsTable.labeldem=1, 1, 0) AS pos_label, if(labelsTable.labeldem=-1, 1, 0) AS neg_label FROM dfTask6ATable INNER JOIN labelsTable ON dfTask6ATable.id = labelsTable.Input_id")
    dfTask6B.registerTempTable("dfTask6BTable")

    pos = sqlContext.sql('select pos_label as label, features from dfTask6BTable')
    neg = sqlContext.sql('select neg_label as label, features from dfTask6BTable')

    if(not os.path.exists("dem/neg.model") or not os.path.exists("dem/pos.model")):
        # Initialize two logistic regression models.
        # Replace labelCol with the column containing the label, and featuresCol with the column containing the features.
        poslr = LogisticRegression(labelCol="label", featuresCol="features", maxIter=10).setThreshold(0.2)
        neglr = LogisticRegression(labelCol="label", featuresCol="features", maxIter=10).setThreshold(0.25)
        # This is a binary classifier so we need an evaluator that knows how to deal with binary classifiers.
        posEvaluator = BinaryClassificationEvaluator()
        negEvaluator = BinaryClassificationEvaluator()
        # There are a few parameters associated with logistic regression. We do not know what they are a priori.
        # We do a grid search to find the best parameters. We can replace [1.0] with a list of values to try.
        # We will assume the parameter is 1.0. Grid search takes forever.
        posParamGrid = ParamGridBuilder().addGrid(poslr.regParam, [1.0]).build()
        negParamGrid = ParamGridBuilder().addGrid(neglr.regParam, [1.0]).build()
        # We initialize a 5 fold cross-validation pipeline.
        posCrossval = CrossValidator(
            estimator=poslr,
            evaluator=posEvaluator,
            estimatorParamMaps=posParamGrid,
            numFolds=5)
        negCrossval = CrossValidator(
            estimator=neglr,
            evaluator=negEvaluator,
            estimatorParamMaps=negParamGrid,
            numFolds=5)
        # Although crossvalidation creates its own train/test sets for
        # tuning, we still need a labeled test set, because it is not
        # accessible from the crossvalidator (argh!)
        # Split the data 50/50
        posTrain, posTest = pos.randomSplit([0.5, 0.5])
        negTrain, negTest = neg.randomSplit([0.5, 0.5])
        # Train the models
        print("Training positive classifier...")
        posModel = posCrossval.fit(posTrain)
        print("Training negative classifier...")
        negModel = negCrossval.fit(negTrain)

        # Once we train the models, we don't want to do it again. We can save the models and load them again later.
        posModel.write().overwrite().save("dem/pos.model")
        negModel.write().overwrite().save("dem/neg.model")

    # TO LOAD BACK IN
    posModel = CrossValidatorModel.load("dem/pos.model")
    negModel = CrossValidatorModel.load("dem/neg.model")

    # Task 8
    dfTask8 = sqlContext.sql('SELECT commentsTable.id, commentsTable.body, commentsTable.created_utc, commentsTable.author_flair_text, submissionsTable.title, commentsTable.score AS comment_score, submissionsTable.score AS story_score FROM commentsTable INNER JOIN submissionsTable ON RIGHT(commentsTable.link_id, 6)=submissionsTable.id')
    dfTask8 = dfTask8.sample(False, 0.05, None)

    #TASK 4 and TASK 5
    def do_something(text):
        return parser.sanitize(text)

    udf_func = udf(do_something, ArrayType(StringType()))
    dfTask9_1 = dfTask8.withColumn("udf_results", udf_func(col("body")))

    #TASK 6A and Task 6B
    model = CountVectorizerModel.load("cvModel")
    dfTask9_2 = model.transform(dfTask9_1)
    dfTask9_2.registerTempTable("dfTask9_2Table")

    # Task 9
    dfTask9_3 = sqlContext.sql("SELECT * FROM dfTask9_2Table WHERE dfTask9_2Table.body NOT LIKE '%/s%' AND dfTask9_2Table.body NOT LIKE '&gt%'")
    dfTask9_3.registerTempTable("dfTask9_3Table")

    posResult_1 = posModel.transform(dfTask9_3)
    posResult_1.registerTempTable("posResult_1Table")
    posResult_2 = sqlContext.sql("SELECT posResult_1Table.id, posResult_1Table.body, posResult_1Table.author_flair_text, posResult_1Table.created_utc, posResult_1Table.title, posResult_1Table.comment_score, posResult_1Table.story_score, posResult_1Table.features, posResult_1Table.prediction AS pos FROM posResult_1Table")
    finalResult_1 = negModel.transform(posResult_2)
    finalResult_1.registerTempTable("finalResult_1Table")
    finalResult_2 = sqlContext.sql("SELECT finalResult_1Table.id, finalResult_1Table.body, finalResult_1Table.created_utc, finalResult_1Table.author_flair_text, finalResult_1Table.title, finalResult_1Table.comment_score, finalResult_1Table.story_score, finalResult_1Table.pos, finalResult_1Table.prediction AS neg FROM finalResult_1Table")
    finalResult_2.registerTempTable("finalResult_2Table")

    # Task 10
    if(not os.path.exists("EC/question1Dem.csv")):
        question1 = sqlContext.sql("SELECT (100 * sum(pos) / COUNT(*)) AS percent_pos, (100 * sum(neg) / COUNT(*)) AS percent_neg FROM finalResult_2Table")
        question1.repartition(1).write.format("com.databricks.spark.csv").option("header", "true").save("EC/question1Dem.csv")

    if(not os.path.exists("EC/question2Dem.csv")):
        question2 = sqlContext.sql("SELECT DATE(from_unixtime(finalResult_2Table.created_utc)) AS date, 100*SUM(finalResult_2Table.pos)/COUNT(*) AS percent_pos, 100*SUM(finalResult_2Table.neg)/COUNT(*) AS percent_neg FROM finalResult_2Table GROUP BY date ORDER BY date")
        question2.repartition(1).write.format("com.databricks.spark.csv").option("header", "true").save("EC/question2Dem.csv")

    if(not os.path.exists("EC/question3Dem.csv")):
        question3 = sqlContext.sql("SELECT finalResult_2Table.author_flair_text AS place, 100*SUM(finalResult_2Table.pos)/COUNT(*) AS percent_pos, 100*SUM(finalResult_2Table.neg)/COUNT(*) AS percent_neg FROM finalResult_2Table GROUP BY place ORDER BY place")
        question3.repartition(1).write.format("com.databricks.spark.csv").option("header", "true").save("EC/question3Dem.csv")

def gop(context):
    #TASK 1

    # Read from JSON
    #comments = sqlContext.read.json("comments-minimal.json.bz2")
    #comments.registerTempTable("commentsTable")
    #submissions = sqlContext.read.json("submissions.json.bz2")
    #submissions.registerTempTable("submissionsTable")

    # Write the Parquets
    #comments.write.parquet("comments.parquet")
    #submissions.write.parquet("submissions.parquet")

    # Read the parquets
    comments = sqlContext.read.parquet("comments.parquet")
    comments.registerTempTable("commentsTable")
    submissions = sqlContext.read.parquet("submissions.parquet")
    submissions.registerTempTable("submissionsTable")

    # Read the CSV
    labels = sqlContext.read.format('csv').options(header='true', inferSchema='true').load("labeled_data.csv")
    labels.registerTempTable("labelsTable")

    #TASK 2
    dfTask2 = sqlContext.sql("SELECT commentsTable.* FROM commentsTable INNER JOIN labelsTable ON commentsTable.id = labelsTable.Input_id")

    #TASK 4 and TASK 5
    def do_something(text):
        return parser.sanitize(text)

    udf_func = udf(do_something, ArrayType(StringType()))
    dfTask4 = dfTask2.withColumn("udf_results", udf_func(col("body")))

    #TASK 6A and Task 6B
    if(not os.path.exists("cvModel")):
        cv = CountVectorizer(inputCol="udf_results", outputCol="features", binary=True, minDF=5.0)
        model = cv.fit(dfTask4)
        model.write().overwrite().save("cvModel")

    model = CountVectorizerModel.load("cvModel")
    dfTask6A = model.transform(dfTask4)
    dfTask6A.registerTempTable("dfTask6ATable")
    dfTask6B = sqlContext.sql("SELECT dfTask6ATable.*, IF(labelsTable.labelgop=1, 1, 0) AS pos_label, if(labelsTable.labelgop=-1, 1, 0) AS neg_label FROM dfTask6ATable INNER JOIN labelsTable ON dfTask6ATable.id = labelsTable.Input_id")
    dfTask6B.registerTempTable("dfTask6BTable")

    pos = sqlContext.sql('select pos_label as label, features from dfTask6BTable')
    neg = sqlContext.sql('select neg_label as label, features from dfTask6BTable')

    if(not os.path.exists("gop/neg.model") or not os.path.exists("gop/pos.model")):
        # Initialize two logistic regression models.
        # Replace labelCol with the column containing the label, and featuresCol with the column containing the features.
        poslr = LogisticRegression(labelCol="label", featuresCol="features", maxIter=10).setThreshold(0.2)
        neglr = LogisticRegression(labelCol="label", featuresCol="features", maxIter=10).setThreshold(0.25)
        # This is a binary classifier so we need an evaluator that knows how to deal with binary classifiers.
        posEvaluator = BinaryClassificationEvaluator()
        negEvaluator = BinaryClassificationEvaluator()
        # There are a few parameters associated with logistic regression. We do not know what they are a priori.
        # We do a grid search to find the best parameters. We can replace [1.0] with a list of values to try.
        # We will assume the parameter is 1.0. Grid search takes forever.
        posParamGrid = ParamGridBuilder().addGrid(poslr.regParam, [1.0]).build()
        negParamGrid = ParamGridBuilder().addGrid(neglr.regParam, [1.0]).build()
        # We initialize a 5 fold cross-validation pipeline.
        posCrossval = CrossValidator(
            estimator=poslr,
            evaluator=posEvaluator,
            estimatorParamMaps=posParamGrid,
            numFolds=5)
        negCrossval = CrossValidator(
            estimator=neglr,
            evaluator=negEvaluator,
            estimatorParamMaps=negParamGrid,
            numFolds=5)
        # Although crossvalidation creates its own train/test sets for
        # tuning, we still need a labeled test set, because it is not
        # accessible from the crossvalidator (argh!)
        # Split the data 50/50
        posTrain, posTest = pos.randomSplit([0.5, 0.5])
        negTrain, negTest = neg.randomSplit([0.5, 0.5])
        # Train the models
        print("Training positive classifier...")
        posModel = posCrossval.fit(posTrain)
        print("Training negative classifier...")
        negModel = negCrossval.fit(negTrain)

        # Once we train the models, we don't want to do it again. We can save the models and load them again later.
        posModel.write().overwrite().save("gop/pos.model")
        negModel.write().overwrite().save("gop/neg.model")

    # TO LOAD BACK IN
    posModel = CrossValidatorModel.load("gop/pos.model")
    negModel = CrossValidatorModel.load("gop/neg.model")

    # Task 8
    dfTask8 = sqlContext.sql('SELECT commentsTable.id, commentsTable.body, commentsTable.created_utc, commentsTable.author_flair_text, submissionsTable.title, commentsTable.score AS comment_score, submissionsTable.score AS story_score FROM commentsTable INNER JOIN submissionsTable ON RIGHT(commentsTable.link_id, 6)=submissionsTable.id')
    dfTask8 = dfTask8.sample(False, 0.05, None)

    #TASK 4 and TASK 5
    def do_something(text):
        return parser.sanitize(text)

    udf_func = udf(do_something, ArrayType(StringType()))
    dfTask9_1 = dfTask8.withColumn("udf_results", udf_func(col("body")))

    #TASK 6A and Task 6B
    model = CountVectorizerModel.load("cvModel")
    dfTask9_2 = model.transform(dfTask9_1)
    dfTask9_2.registerTempTable("dfTask9_2Table")

    # Task 9
    dfTask9_3 = sqlContext.sql("SELECT * FROM dfTask9_2Table WHERE dfTask9_2Table.body NOT LIKE '%/s%' AND dfTask9_2Table.body NOT LIKE '&gt%'")
    dfTask9_3.registerTempTable("dfTask9_3Table")

    posResult_1 = posModel.transform(dfTask9_3)
    posResult_1.registerTempTable("posResult_1Table")
    posResult_2 = sqlContext.sql("SELECT posResult_1Table.id, posResult_1Table.body, posResult_1Table.author_flair_text, posResult_1Table.created_utc, posResult_1Table.title, posResult_1Table.comment_score, posResult_1Table.story_score, posResult_1Table.features, posResult_1Table.prediction AS pos FROM posResult_1Table")
    finalResult_1 = negModel.transform(posResult_2)
    finalResult_1.registerTempTable("finalResult_1Table")
    finalResult_2 = sqlContext.sql("SELECT finalResult_1Table.id, finalResult_1Table.body, finalResult_1Table.created_utc, finalResult_1Table.author_flair_text, finalResult_1Table.title, finalResult_1Table.comment_score, finalResult_1Table.story_score, finalResult_1Table.pos, finalResult_1Table.prediction AS neg FROM finalResult_1Table")
    finalResult_2.registerTempTable("finalResult_2Table")

    # Task 10
    if(not os.path.exists("EC/question1Gop.csv")):
        question1 = sqlContext.sql("SELECT (100 * sum(pos) / COUNT(*)) AS percent_pos, (100 * sum(neg) / COUNT(*)) AS percent_neg FROM finalResult_2Table")
        question1.repartition(1).write.format("com.databricks.spark.csv").option("header", "true").save("EC/question1Gop.csv")

    if(not os.path.exists("EC/question2Gop.csv")):
        question2 = sqlContext.sql("SELECT DATE(from_unixtime(finalResult_2Table.created_utc)) AS date, 100*SUM(finalResult_2Table.pos)/COUNT(*) AS percent_pos, 100*SUM(finalResult_2Table.neg)/COUNT(*) AS percent_neg FROM finalResult_2Table GROUP BY date ORDER BY date")
        question2.repartition(1).write.format("com.databricks.spark.csv").option("header", "true").save("EC/question2Gop.csv")

    if(not os.path.exists("EC/question3Gop.csv")):
        question3 = sqlContext.sql("SELECT finalResult_2Table.author_flair_text AS place, 100*SUM(finalResult_2Table.pos)/COUNT(*) AS percent_pos, 100*SUM(finalResult_2Table.neg)/COUNT(*) AS percent_neg FROM finalResult_2Table GROUP BY place ORDER BY place")
        question3.repartition(1).write.format("com.databricks.spark.csv").option("header", "true").save("EC/question3Gop.csv")

def main(context):

    # dem(context)
    # gop(context)

    # SAVED PARQUETS
    # comments is the comments-minimal.json
    # submissions is the submissions.json
    # task7 is the result of the count vectorizer
    # commentsFull is the comments-minimal.json joined with submissions with the sarcasm removed and the &gt removed

    #TASK 1

    # Read from JSON
    #comments = sqlContext.read.json("comments-minimal.json.bz2")
    #comments.registerTempTable("commentsTable")
    #submissions = sqlContext.read.json("submissions.json.bz2")
    #submissions.registerTempTable("submissionsTable")

    # Write the Parquets
    #comments.write.parquet("comments.parquet")
    #submissions.write.parquet("submissions.parquet")

    # Read the parquets
    comments = sqlContext.read.parquet("comments.parquet")
    comments.registerTempTable("commentsTable")
    submissions = sqlContext.read.parquet("submissions.parquet")
    submissions.registerTempTable("submissionsTable")

    # Read the CSV
    labels = sqlContext.read.format('csv').options(header='true', inferSchema='true').load("labeled_data.csv")
    labels.registerTempTable("labelsTable")

    #TASK 2
    dfTask2 = sqlContext.sql("SELECT commentsTable.* FROM commentsTable INNER JOIN labelsTable ON commentsTable.id = labelsTable.Input_id")

    #TASK 4 and TASK 5
    def do_something(text):
        return parser.sanitize(text)

    udf_func = udf(do_something, ArrayType(StringType()))
    dfTask4 = dfTask2.withColumn("udf_results", udf_func(col("body")))

    #TASK 6A and Task 6B
    if(not os.path.exists("cvModel")):
        cv = CountVectorizer(inputCol="udf_results", outputCol="features", binary=True, minDF=5.0)
        model = cv.fit(dfTask4)
        model.write().overwrite().save("cvModel")

    model = CountVectorizerModel.load("cvModel")
    dfTask6A = model.transform(dfTask4)
    dfTask6A.registerTempTable("dfTask6ATable")
    dfTask6B = sqlContext.sql("SELECT dfTask6ATable.*, IF(labelsTable.labeldjt=1, 1, 0) AS pos_label, if(labelsTable.labeldjt=-1, 1, 0) AS neg_label FROM dfTask6ATable INNER JOIN labelsTable ON dfTask6ATable.id = labelsTable.Input_id")
    dfTask6B.registerTempTable("dfTask6BTable")

    pos = sqlContext.sql('select pos_label as label, features from dfTask6BTable')
    neg = sqlContext.sql('select neg_label as label, features from dfTask6BTable')

    if(not os.path.exists("www/neg.model") or not os.path.exists("www/pos.model")):
        # Initialize two logistic regression models.
        # Replace labelCol with the column containing the label, and featuresCol with the column containing the features.
        poslr = LogisticRegression(labelCol="label", featuresCol="features", maxIter=10).setThreshold(0.2)
        neglr = LogisticRegression(labelCol="label", featuresCol="features", maxIter=10).setThreshold(0.25)
        # This is a binary classifier so we need an evaluator that knows how to deal with binary classifiers.
        posEvaluator = BinaryClassificationEvaluator()
        negEvaluator = BinaryClassificationEvaluator()
        # There are a few parameters associated with logistic regression. We do not know what they are a priori.
        # We do a grid search to find the best parameters. We can replace [1.0] with a list of values to try.
        # We will assume the parameter is 1.0. Grid search takes forever.
        posParamGrid = ParamGridBuilder().addGrid(poslr.regParam, [1.0]).build()
        negParamGrid = ParamGridBuilder().addGrid(neglr.regParam, [1.0]).build()
        # We initialize a 5 fold cross-validation pipeline.
        posCrossval = CrossValidator(
            estimator=poslr,
            evaluator=posEvaluator,
            estimatorParamMaps=posParamGrid,
            numFolds=2)
        negCrossval = CrossValidator(
            estimator=neglr,
            evaluator=negEvaluator,
            estimatorParamMaps=negParamGrid,
            numFolds=2)
        # Although crossvalidation creates its own train/test sets for
        # tuning, we still need a labeled test set, because it is not
        # accessible from the crossvalidator (argh!)
        # Split the data 50/50
        posTrain, posTest = pos.randomSplit([0.5, 0.5])
        negTrain, negTest = neg.randomSplit([0.5, 0.5])
        # Train the models
        print("Training positive classifier...")
        posModel = posCrossval.fit(posTrain)
        print("Training negative classifier...")
        negModel = negCrossval.fit(negTrain)

        # Once we train the models, we don't want to do it again. We can save the models and load them again later.
        posModel.write().overwrite().save("www/pos.model")
        negModel.write().overwrite().save("www/neg.model")

    # TO LOAD BACK IN
    posModel = CrossValidatorModel.load("www/pos.model")
    negModel = CrossValidatorModel.load("www/neg.model")

    # Task 8
    dfTask8 = sqlContext.sql('SELECT commentsTable.id, commentsTable.body, commentsTable.created_utc, commentsTable.author_flair_text, submissionsTable.title, commentsTable.score AS comment_score, submissionsTable.score AS story_score FROM commentsTable INNER JOIN submissionsTable ON RIGHT(commentsTable.link_id, 6)=submissionsTable.id')
    dfTask8 = dfTask8.sample(False, 0.1, None)

    #TASK 4 and TASK 5
    def do_something(text):
        return parser.sanitize(text)

    udf_func = udf(do_something, ArrayType(StringType()))
    dfTask9_1 = dfTask8.withColumn("udf_results", udf_func(col("body")))

    #TASK 6A and Task 6B
    model = CountVectorizerModel.load("cvModel")
    dfTask9_2 = model.transform(dfTask9_1)
    dfTask9_2.registerTempTable("dfTask9_2Table")

    # Task 9
    dfTask9_3 = sqlContext.sql("SELECT * FROM dfTask9_2Table WHERE dfTask9_2Table.body NOT LIKE '%/s%' AND dfTask9_2Table.body NOT LIKE '&gt%'")
    dfTask9_3.registerTempTable("dfTask9_3Table")

    posResult_1 = posModel.transform(dfTask9_3)
    posResult_1.registerTempTable("posResult_1Table")
    posResult_2 = sqlContext.sql("SELECT posResult_1Table.id, posResult_1Table.body, posResult_1Table.author_flair_text, posResult_1Table.created_utc, posResult_1Table.title, posResult_1Table.comment_score, posResult_1Table.story_score, posResult_1Table.features, posResult_1Table.prediction AS pos FROM posResult_1Table")
    finalResult_1 = negModel.transform(posResult_2)
    finalResult_1.registerTempTable("finalResult_1Table")
    finalResult_2 = sqlContext.sql("SELECT finalResult_1Table.id, finalResult_1Table.body, finalResult_1Table.created_utc, finalResult_1Table.author_flair_text, finalResult_1Table.title, finalResult_1Table.comment_score, finalResult_1Table.story_score, finalResult_1Table.pos, finalResult_1Table.prediction AS neg FROM finalResult_1Table")
    finalResult_2.registerTempTable("finalResult_2Table")

    if(not os.path.exists("final.parquet")):
        finalResult_2.write.parquet("final.parquet")

    final = sqlContext.read.parquet("final.parquet")
    final.registerTempTable("finalTable")

    # Task 10
    if(not os.path.exists("question1.csv")):
        question1 = sqlContext.sql("SELECT (100 * sum(pos) / COUNT(*)) AS percent_pos, (100 * sum(neg) / COUNT(*)) AS percent_neg FROM finalTable")
        question1.repartition(1).write.format("com.databricks.spark.csv").option("header", "true").save("question1.csv")

    if(not os.path.exists("question2.csv")):
        question2 = sqlContext.sql("SELECT DATE(from_unixtime(finalTable.created_utc)) AS date, 100*SUM(finalTable.pos)/COUNT(*) AS percent_pos, 100*SUM(finalTable.neg)/COUNT(*) AS percent_neg FROM finalTable GROUP BY date ORDER BY date")
        question2.repartition(1).write.format("com.databricks.spark.csv").option("header", "true").save("question2.csv")

    if(not os.path.exists("question3.csv")):
        question3 = sqlContext.sql("SELECT finalTable.author_flair_text AS place, 100*SUM(finalTable.pos)/COUNT(*) AS percent_pos, 100*SUM(finalTable.neg)/COUNT(*) AS percent_neg FROM finalTable GROUP BY place ORDER BY place")
        question3.repartition(1).write.format("com.databricks.spark.csv").option("header", "true").save("question3.csv")

    if(not os.path.exists("question4_comment.csv")):
        question4_comment = sqlContext.sql("SELECT finalTable.comment_score AS comment_score, 100*SUM(finalTable.pos)/COUNT(*) AS percent_pos, 100*SUM(finalTable.neg)/COUNT(*) AS percent_neg FROM finalTable GROUP BY comment_score ORDER BY comment_score")
        question4_comment.repartition(1).write.format("com.databricks.spark.csv").option("header", "true").save("question4_comment.csv")

    if(not os.path.exists("question4_story.csv")):
        question4_story = sqlContext.sql("SELECT finalTable.story_score AS story_score, 100*SUM(finalTable.pos)/COUNT(*) AS percent_pos, 100*SUM(finalTable.neg)/COUNT(*) AS percent_neg FROM finalTable GROUP BY story_score ORDER BY story_score")
        question4_story.repartition(1).write.format("com.databricks.spark.csv").option("header", "true").save("question4_story.csv")

if __name__ == "__main__":
    conf = SparkConf().setAppName("CS143 Project 2B")
    conf = conf.setMaster("local[*]")
    sc   = SparkContext(conf=conf)
    sqlContext = SQLContext(sc)
    sc.addPyFile("parser.py")
    import parser
    main(sqlContext)
