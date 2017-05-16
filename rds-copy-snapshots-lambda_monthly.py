from __future__ import print_function
from dateutil import parser, relativedelta
from boto3 import client
import datetime

# List of database identifiers, or "all" for all databases
# eg. ["db-name1", "db-name2"] or ["all"]
INSTANCES = ["db-name-01"]

# The number of months to keep ONE snapshot per month
MONTHS = 14

# three character prefix for snapshot naming : "mo-" = monthly "wk-" = weekly
str_snap_name_prefx="mo-"

# AWS region in which the db instances exist
REGION = "us-east-1"

# ensure all snaps return a SnapshotCreateTime - Snapshots in progress will not have a timestamp until completed
def byTimestamp(snap):  
    if 'SnapshotCreateTime' in snap:
        return datetime.datetime.isoformat(snap['SnapshotCreateTime'])
    else:
        return datetime.datetime.isoformat(datetime.datetime.now())


def copy_snapshots(rds, snaps):
    newest = snaps[-1]
    rds.copy_db_snapshot(
        SourceDBSnapshotIdentifier=newest['DBSnapshotIdentifier'],
        TargetDBSnapshotIdentifier=str_snap_name_prefx + newest['DBSnapshotIdentifier'][4:],
        CopyTags=True
    )
    print("Snapshot {} copied to {}".format(
          newest['DBSnapshotIdentifier'],
          str_snap_name_prefx + newest['DBSnapshotIdentifier'][4:])
          )


def purge_snapshots(rds, id, snaps, counts):
    newest = snaps[-1]
    prev_start_date = None
    delete_count = 0
    keep_count = 0

    print("---- RESULTS FOR {} ({} snapshots) ----".format(id, len(snaps)))

    for snap in snaps:
#        snap_date = snap['SnapshotCreateTime']
        if 'SnapshotCreateTime' in snap:
            snap_date = snap['SnapshotCreateTime']
        else:
            snap_date = NOW
            
        snap_age = NOW - snap_date
        # Monthly
        type_str = "month"
        start_date_str = snap_date.strftime("%Y-%m")
        if (start_date_str != prev_start_date and
                snap_date > DELETE_BEFORE_DATE):
            # Keep it
            prev_start_date = start_date_str
            print("Keeping {}: {}, {} unix epoc days old - {} of {}".format(
                  snap['DBSnapshotIdentifier'], snap_date, snap_age.days,
                  type_str, start_date_str)
                  )
            keep_count += 1
        else:
            # Never delete the newest snapshot
            if snap['DBSnapshotIdentifier'] == newest['DBSnapshotIdentifier']:
                print(("Keeping {}: {}, {} hours old - will never"
                      " delete newest snapshot").format(
                      snap['DBSnapshotIdentifier'], snap_date,
                      snap_age.seconds/3600)
                      )
                keep_count += 1
            else:
                # Delete it
                print("- Deleting{} {}: {}, {} days old".format(
                      NOT_REALLY_STR, snap['DBSnapshotIdentifier'],
                      snap_date, snap_age.days)
                      )
                if NOOP is False:
                    rds.delete_db_snapshot(
                        DBSnapshotIdentifier=snap['DBSnapshotIdentifier']
                        )
                delete_count += 1
    counts[id] = [delete_count, keep_count]


def get_snaps(rds, instance, snap_type):
    if len(INSTANCES) == INSTANCES.count("all"):
        snapshots = rds.describe_db_snapshots(
                    SnapshotType=snap_type)['DBSnapshots']
    else:
        snapshots = rds.describe_db_snapshots(
                    SnapshotType=snap_type,
                    DBInstanceIdentifier=instance)['DBSnapshots']
#    return sorted(snapshots, key=lambda x:x['SnapshotCreateTime'])
    return sorted(snapshots, key=byTimestamp, reverse=False)


def print_summary(counts):
    print("\nSUMMARY:\n")
    for id, (deleted, kept) in counts.iteritems():
        print("{}:".format(id))
        print("  deleted: {}{}".format(
              deleted, NOT_REALLY_STR if deleted > 0 else "")
              )
        print("  kept:    {}".format(kept))
        print("-------------------------------------------\n")


def main(event, context):
    global NOW
    global DELETE_BEFORE_DATE
    global NOOP
    global NOT_REALLY_STR

    NOW = parser.parse(event['time'])
    DELETE_BEFORE_DATE = (NOW - relativedelta.relativedelta(months=MONTHS))
    NOOP = event['noop'] if 'noop' in event else False
    NOT_REALLY_STR = " (not really)" if NOOP is not False else ""
    rds = client("rds", region_name=REGION)

    if INSTANCES:
        for instance in INSTANCES:
            instance_counts = {}
            snapshots_auto = get_snaps(rds, instance, 'automated')
            if snapshots_auto:
                copy_snapshots(rds, snapshots_auto)
            else:
                print("No auto snapshots found for instance: {}".format(
                      instance)
                      )
            snapshots_manual = get_snaps(rds, instance, 'manual')
            if snapshots_manual:
                print("\nNumber of Monthly Snaps to retain = ",MONTHS," \n" )
                print("The variable NOW is set to ",NOW," \n")
                print("Snapshots will be deleted prior to ",DELETE_BEFORE_DATE," \n" ) 
                purge_snapshots(rds, instance,
                                snapshots_manual, instance_counts)
                print_summary(instance_counts)
            else:
                print("No manual snapshots found for instance: {}".format(
                      instance)
                      )
    else:
        print("You must populate the INSTANCES variable.")